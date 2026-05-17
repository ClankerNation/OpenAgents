const { expect } = require("chai");
const { ethers, artifacts } = require("hardhat");

const HARDHAT_PRIVATE_KEY =
  "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80";

async function waitForPendingDeployment(pending) {
  let settled = false;
  let result;
  let failure;

  pending
    .then((value) => {
      settled = true;
      result = value;
    })
    .catch((error) => {
      settled = true;
      failure = error;
    });

  for (let i = 0; i < 10 && !settled; i++) {
    await ethers.provider.send("evm_mine", []);
    await new Promise((resolve) => setTimeout(resolve, 10));
  }

  if (failure) {
    throw failure;
  }

  if (!settled) {
    throw new Error("Deployment did not resolve after mining confirmation blocks");
  }

  return result;
}

describe("OpenAgentsSDK deployContract", function () {
  let sdk;
  let artifact;

  beforeEach(async function () {
    const { OpenAgentsSDK } = await import("../sdk/src/index.ts");
    sdk = new OpenAgentsSDK({
      name: "Test Agent",
      endpoint: "http://localhost:3000",
      privateKey: HARDHAT_PRIVATE_KEY,
      rpcUrl: "http://127.0.0.1:8545",
      provider: ethers.provider,
      registryAddress: ethers.ZeroAddress,
      routerAddress: ethers.ZeroAddress,
    });

    artifact = await artifacts.readArtifact("AgentToken");
  });

  it("deploys a contract with constructor args and returns receipt metadata", async function () {
    const result = await sdk.deployContract(
      artifact.abi,
      artifact.bytecode,
      ["Agent Token", "AGT", ethers.parseEther("1000")]
    );

    expect(result.contract.target).to.properAddress;
    expect(result.receipt.contractAddress).to.equal(result.contract.target);
    expect(result.receipt.hash).to.match(/^0x[0-9a-fA-F]{64}$/);
    expect(result.receipt.gasUsed).to.be.a("bigint");
    expect(result.receipt.blockNumber).to.be.a("number");

    expect(await result.contract.name()).to.equal("Agent Token");
    expect(await result.contract.symbol()).to.equal("AGT");
    expect(await result.contract.totalSupply()).to.equal(ethers.parseEther("1000"));
  });

  it("waits the requested number of confirmation blocks", async function () {
    const pending = sdk.deployContract(
      artifact.abi,
      artifact.bytecode,
      ["Delayed Token", "DLT", 1n],
      { confirmations: 2 }
    );

    const result = await waitForPendingDeployment(pending);
    expect(result.receipt.confirmations).to.be.at.least(2);
  });

  it("passes deployment overrides to the contract factory", async function () {
    const gasLimit = 5_000_000n;
    const result = await sdk.deployContract(
      artifact.abi,
      artifact.bytecode,
      ["Override Token", "OVR", 1n],
      { gasLimit }
    );

    expect(result.receipt.contractAddress).to.equal(await result.contract.getAddress());
    const tx = await ethers.provider.getTransaction(result.receipt.hash);
    expect(tx.gasLimit).to.equal(gasLimit);
  });
});
