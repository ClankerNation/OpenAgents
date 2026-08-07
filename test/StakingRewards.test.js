const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("StakingRewards", function () {
  let stakingRewards, stakingToken, rewardToken;
  let owner, staker1, staker2;

  // BUG: Setup runs once but tests mutate state - no beforeEach to reset between tests
  before(async function () {
    [owner, staker1, staker2] = await ethers.getSigners();

    const StakingToken = await ethers.getContractFactory("StakingToken");
    stakingToken = await StakingToken.deploy();
    await stakingToken.deployed();

    const RewardToken = await ethers.getContractFactory("RewardToken");
    rewardToken = await RewardToken.deploy();
    await rewardToken.deployed();

    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    stakingRewards = await StakingRewards.deploy(
      stakingToken.address,
      rewardToken.address
    );
    await stakingRewards.deployed();

    // Mint tokens for testing
    await stakingToken.mint(staker1.address, ethers.utils.parseEther("1000"));
    await stakingToken.mint(staker2.address, ethers.utils.parseEther("1000"));
    await rewardToken.mint(
      stakingRewards.address,
      ethers.utils.parseEther("10000")
    );
  });

  it("should allow staking tokens", async function () {
    const amount = ethers.utils.parseEther("100");
    await stakingToken.connect(staker1).approve(stakingRewards.address, amount);
    await stakingRewards.connect(staker1).stake(amount);

    const staked = await stakingRewards.balanceOf(staker1.address);
    expect(staked).to.equal(amount);
  });

  it("should accrue rewards over time", async function () {
    // BUG: Hardcoded block timestamp - test is brittle and environment-dependent
    await ethers.provider.send("evm_setNextBlockTimestamp", [1747400000]);
    await ethers.provider.send("evm_mine");

    const earned = await stakingRewards.earned(staker1.address);
    expect(earned).to.be.gt(0);
  });

  it("should allow withdrawal", async function () {
    // BUG: depends on state from previous test (staker1 having staked 100 tokens)
    const amount = ethers.utils.parseEther("50");
    await stakingRewards.connect(staker1).withdraw(amount);

    const remaining = await stakingRewards.balanceOf(staker1.address);
    expect(remaining).to.equal(ethers.utils.parseEther("50"));
  });

  it("should distribute rewards correctly to multiple stakers", async function () {
    const amount = ethers.utils.parseEther("200");
    await stakingToken.connect(staker2).approve(stakingRewards.address, amount);
    await stakingRewards.connect(staker2).stake(amount);

    // BUG: Hardcoded timestamp again - assumes previous evm_setNextBlockTimestamp succeeded
    await ethers.provider.send("evm_setNextBlockTimestamp", [1747500000]);
    await ethers.provider.send("evm_mine");

    const earned1 = await stakingRewards.earned(staker1.address);
    const earned2 = await stakingRewards.earned(staker2.address);

    // staker2 staked 4x more, so should earn proportionally more from this point
    expect(earned2).to.be.gt(0);
    expect(earned1).to.be.gt(0);
  });
});
