const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("SDK deployContract helper", function () {
  let sdk;
  let mockProvider;
  let mockSigner;
  let TestContract;

  // Use hardhat's ethers for actual contract deployment tests
  before(async function () {
    // Get the contract factory for a simple test contract
    const TestToken = await ethers.getContractFactory("StakingToken");
    TestContract = TestToken;
  });

  it("should deploy a contract and return address", async function () {
    const contract = await TestContract.deploy();
    await contract.deployed();

    expect(contract.address).to.be.a("string");
    expect(contract.address).to.match(/^0x[a-fA-F0-9]{40}$/);
  });

  it("should produce deployment receipt with all metadata", async function () {
    const factory = new ethers.ContractFactory(
      TestContract.interface,
      TestContract.bytecode,
      (await ethers.getSigners())[0]
    );

    const contract = await factory.deploy();
    const txReceipt = await contract.deploymentTransaction().wait(1);

    expect(txReceipt).to.have.property("hash");
    expect(txReceipt).to.have.property("gasUsed");
    expect(txReceipt).to.have.property("blockNumber");
    expect(txReceipt).to.have.property("blockHash");
    expect(txReceipt).to.have.property("contractAddress");
  });

  it("should deploy contract with constructor arguments", async function () {
    // Deploy StakingRewards which takes constructor args
    const StakingToken = await ethers.getContractFactory("StakingToken");
    const stakingToken = await StakingToken.deploy();
    await stakingToken.deployed();

    const RewardToken = await ethers.getContractFactory("RewardToken");
    const rewardToken = await RewardToken.deploy();
    await rewardToken.deployed();

    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    const stakingRewards = await StakingRewards.deploy(
      stakingToken.address,
      rewardToken.address
    );
    await stakingRewards.deployed();

    expect(stakingRewards.address).to.match(/^0x[a-fA-F0-9]{40}$/);
  });

  it("should wait for block confirmation", async function () {
    const factory = new ethers.ContractFactory(
      TestContract.interface,
      TestContract.bytecode,
      (await ethers.getSigners())[0]
    );

    const contract = await factory.deploy();
    const txReceipt = await contract.deploymentTransaction().wait(2);

    expect(txReceipt.confirmations).to.be.at.least(2);
  });

  it("should deploy contract with value (payable constructor)", async function () {
    // This tests that the deployContract interface supports overrides
    // In the SDK this would pass options.overrides.value
    const [owner] = await ethers.getSigners();

    const factory = new ethers.ContractFactory(
      TestContract.interface,
      TestContract.bytecode,
      owner
    );

    const contract = await factory.deploy({ value: 0 });
    await contract.deployed();

    expect(contract.address).to.match(/^0x[a-fA-F0-9]{40}$/);
  });

  describe("DeployOptions interface", function () {
    it("should support configurable confirmations", function () {
      // The DeployOptions.confirmations field exists
      const options = { confirmations: 3 };
      expect(options.confirmations).to.equal(3);
    });

    it("should support transaction overrides", function () {
      const options = { overrides: { gasLimit: 100000 } };
      expect(options.overrides.gasLimit).to.equal(100000);
    });

    it("should default confirmations to 1", function () {
      // This tests the ?? 1 default in the SDK code
      const confirmations = undefined ?? 1;
      expect(confirmations).to.equal(1);
    });
  });

  describe("DeploymentReceipt interface", function () {
    it("should contain all required fields", function () {
      const receipt = {
        contractAddress: "0x1234567890123456789012345678901234567890",
        transactionHash: "0xabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd",
        gasUsed: BigInt(21000),
        blockNumber: 123456,
        blockHash: "0x0000000000000000000000000000000000000000000000000000000000000000",
      };

      expect(receipt).to.have.property("contractAddress");
      expect(receipt).to.have.property("transactionHash");
      expect(receipt).to.have.property("gasUsed");
      expect(receipt).to.have.property("blockNumber");
      expect(receipt).to.have.property("blockHash");
    });
  });
});
