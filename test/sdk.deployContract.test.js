const assert = require("node:assert/strict");
const { before, describe, it } = require("mocha");
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
  const contract = output.contracts?.["DeployTarget.sol"]?.DeployTarget;
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

describe("OpenAgentsSDK.deployContract", () => {
  let OpenAgentsSDK;
  let signer;
  let compiled;

  before(async () => {
    ({ OpenAgentsSDK } = await import("../sdk/src/index.ts"));
    [signer] = await ethers.getSigners();
    compiled = compileDeployTarget();
  });

  it("deploys with constructor args and returns receipt metadata", async () => {
    const sdk = new OpenAgentsSDK(buildConfig(ethers.Wallet.createRandom().privateKey), {
      provider: signer.provider,
      signer,
    });

    const result = await sdk.deployContract(compiled.abi, compiled.bytecode, [1234n]);

    assert.equal(result.address, await result.contract.getAddress());
    assert.match(result.txHash, /^0x[0-9a-fA-F]{64}$/);
    assert.ok(result.gasUsed > 0n);

    const deployed = new ethers.Contract(result.address, compiled.abi, signer.provider);
    assert.equal(await deployed.value(), 1234n);
  });

  it("waits for configurable confirmation blocks", async () => {
    const sdk = new OpenAgentsSDK(buildConfig(ethers.Wallet.createRandom().privateKey), {
      provider: signer.provider,
      signer,
    });

    const pendingDeployment = sdk.deployContract(
      compiled.abi,
      compiled.bytecode,
      [1n],
      { confirmations: 2 }
    );

    const raceResult = await Promise.race([
      pendingDeployment.then(() => "resolved"),
      new Promise((resolve) => setTimeout(() => resolve("pending"), 100)),
    ]);
    assert.equal(raceResult, "pending");

    await network.provider.send("evm_mine");
    const result = await pendingDeployment;
    const currentBlock = await signer.provider.getBlockNumber();
    assert.ok(currentBlock - result.receipt.blockNumber >= 1);
  });
});
