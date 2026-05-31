const assert = require("node:assert/strict");
const { describe, it, before } = require("mocha");
const hre = require("hardhat");
const solc = require("solc");

const { ethers, network } = hre;

function compileDeployTarget() {
  const input = {
    language: "Solidity",
    sources: {
      "DeployTarget.sol": {
        content: `
          // SPDX-License-Identifier: MIT
          pragma solidity ^0.8.20;
          contract DeployTarget {
            uint256 public value;
            constructor(uint256 _value) {
              value = _value;
            }
          }
        `,
      },
    },
    settings: {
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode.object"],
        },
      },
    },
  };

  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const contract =
    output.contracts["DeployTarget.sol"] &&
    output.contracts["DeployTarget.sol"].DeployTarget;

  if (!contract) {
    throw new Error("Failed to compile DeployTarget");
  }

  return {
    abi: contract.abi,
    bytecode: `0x${contract.evm.bytecode.object}`,
  };
}

function buildConfig(privateKey) {
  return {
    name: "sdk-test-agent",
    endpoint: "https://example.com/agent",
    privateKey,
    rpcUrl: "http://127.0.0.1:8545",
    registryAddress: ethers.ZeroAddress,
    routerAddress: ethers.ZeroAddress,
  };
}

describe("OpenAgentsSDK deployContract", () => {
  let OpenAgentsSDK;
  let signer;
  let compiledContract;

  before(async () => {
    ({ OpenAgentsSDK } = await import("../sdk/src/index.ts"));
    [signer] = await ethers.getSigners();
    compiledContract = compileDeployTarget();
  });

  it("deploys with constructor args and returns deployment metadata", async () => {
    const sdk = new OpenAgentsSDK(buildConfig(ethers.Wallet.createRandom().privateKey), {
      provider: signer.provider,
      signer,
    });
    const initialValue = 1234n;

    const deployment = await sdk.deployContract(
      compiledContract.abi,
      compiledContract.bytecode,
      [initialValue]
    );

    const deployedAddress = await deployment.contract.getAddress();
    assert.equal(deployment.address, deployedAddress);
    assert.match(deployment.txHash, /^0x[0-9a-fA-F]{64}$/);
    assert.ok(deployment.gasUsed > 0n);
    assert.equal(deployment.receipt.contractAddress, deployedAddress);
    assert.equal(deployment.receipt.transactionHash, deployment.txHash);
    assert.equal(deployment.receipt.gasUsed, deployment.gasUsed);
    assert.match(deployment.receipt.blockHash, /^0x[0-9a-fA-F]{64}$/);
    assert.equal(typeof deployment.receipt.blockNumber, "number");

    const deployed = new ethers.Contract(
      deployment.address,
      compiledContract.abi,
      signer.provider
    );
    assert.equal(await deployed.value(), initialValue);
  });

  it("waits for configurable confirmation blocks", async () => {
    const sdk = new OpenAgentsSDK(buildConfig(ethers.Wallet.createRandom().privateKey), {
      provider: signer.provider,
      signer,
    });

    const deployPromise = sdk.deployContract(
      compiledContract.abi,
      compiledContract.bytecode,
      [1n],
      { confirmations: 2 }
    );

    const stateBeforeExtraBlock = await Promise.race([
      deployPromise.then(() => "resolved"),
      new Promise((resolve) => setTimeout(() => resolve("pending"), 100)),
    ]);
    assert.equal(stateBeforeExtraBlock, "pending");

    await network.provider.send("evm_mine");
    const deployment = await deployPromise;

    const currentBlock = await signer.provider.getBlockNumber();
    assert.ok(currentBlock - deployment.receipt.blockNumber >= 1);
  });
});
