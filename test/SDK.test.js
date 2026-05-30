const { expect } = require("chai");
const { ethers } = require("hardhat");

// Register ts-node to require typescript files directly
require("ts-node").register();
const { OpenAgentsSDK } = require("../sdk/src/index.ts");

describe("OpenAgentsSDK - deployContract", function () {
  let sdk;
  let owner;
  let stakingTokenAddress, rewardTokenAddress;

  before(async function () {
    [owner] = await ethers.getSigners();

    // Deploy mock tokens first
    const StakingToken = await ethers.getContractFactory("StakingToken");
    const stakingToken = await StakingToken.deploy();
    await stakingToken.waitForDeployment();
    stakingTokenAddress = await stakingToken.getAddress();

    const RewardToken = await ethers.getContractFactory("RewardToken");
    const rewardToken = await RewardToken.deploy();
    await rewardToken.waitForDeployment();
    rewardTokenAddress = await rewardToken.getAddress();

    // Initialize SDK with dummy addresses and override private provider/signer
    sdk = new OpenAgentsSDK({
      name: "test-agent",
      endpoint: "http://localhost:8080",
      privateKey: owner.privateKey || "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80", // standard Hardhat private key
      rpcUrl: "http://127.0.0.1:8545",
      registryAddress: ethers.ZeroAddress,
      routerAddress: ethers.ZeroAddress
    });

    // Override the private provider and signer to use Hardhat's in-memory ones
    sdk.provider = ethers.provider;
    sdk.signer = owner;
  });

  it("should deploy contract successfully with constructor arguments and wait for confirmation", async function () {
    const StakingRewardsFactory = await ethers.getContractFactory("StakingRewards");
    const abi = JSON.parse(StakingRewardsFactory.interface.formatJson());
    const bytecode = StakingRewardsFactory.bytecode;

    const result = await sdk.deployContract(
      abi,
      bytecode,
      [stakingTokenAddress, rewardTokenAddress],
      1
    );

    // Verify address
    expect(result.address).to.properAddress;

    // Verify contract instance
    expect(result.contract).to.not.be.undefined;
    const contractStakingToken = await result.contract.stakingToken();
    expect(contractStakingToken).to.equal(stakingTokenAddress);

    // Verify receipt metadata
    expect(result.receipt).to.not.be.undefined;
    expect(result.receipt.contractAddress).to.equal(result.address);
    expect(result.receipt.transactionHash).to.not.be.undefined;
    expect(result.receipt.gasUsed).to.be.gt(0n);
    expect(result.receipt.blockNumber).to.be.gt(0);
  });
});
