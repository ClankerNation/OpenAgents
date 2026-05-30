const { expect } = require("chai");
const { ethers, artifacts } = require("hardhat");
require("ts-node/register");
const { OpenAgentsSDK } = require("../sdk/src/index");

describe("OpenAgentsSDK Contract Deployment", function () {
  let sdk;
  let owner;

  before(async function () {
    [owner] = await ethers.getSigners();

    sdk = new OpenAgentsSDK({
      name: "test-agent",
      endpoint: "http://localhost:3000",
      privateKey: "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
      rpcUrl: "http://localhost:8545",
      registryAddress: ethers.ZeroAddress,
      routerAddress: ethers.ZeroAddress,
    });

    // Override provider and signer with in-process Hardhat ones for testing
    sdk.provider = ethers.provider;
    sdk.signer = owner;
  });

  it("should deploy contract successfully with args and wait for confirmation", async function () {
    // Load artifact of StakingToken (which has no constructor arguments)
    const tokenArtifact = await artifacts.readArtifact("StakingToken");
    
    // Deploy StakingToken using SDK helper
    const result = await sdk.deployContract(
      tokenArtifact.abi,
      tokenArtifact.bytecode,
      [],
      1 // 1 confirmation block
    );

    expect(result.contract).to.not.be.undefined;
    expect(result.receipt).to.not.be.undefined;
    expect(result.receipt.address).to.equal(result.contract.target);
    expect(result.receipt.txHash).to.not.be.undefined;
    expect(result.receipt.gasUsed).to.be.gt(0n);

    // Load artifact of MultiTokenStaking (which has constructor arguments)
    const stakingArtifact = await artifacts.readArtifact("MultiTokenStaking");
    const rewardTokenAddress = result.receipt.address;
    const rewardPerSecond = ethers.parseEther("1");

    // Deploy MultiTokenStaking using SDK helper with constructor arguments
    const resultStaking = await sdk.deployContract(
      stakingArtifact.abi,
      stakingArtifact.bytecode,
      [rewardTokenAddress, rewardPerSecond],
      1
    );

    expect(resultStaking.contract).to.not.be.undefined;
    expect(resultStaking.receipt).to.not.be.undefined;
    expect(resultStaking.receipt.address).to.equal(resultStaking.contract.target);
    expect(resultStaking.receipt.txHash).to.not.be.undefined;
    expect(resultStaking.receipt.gasUsed).to.be.gt(0n);
  });
});
