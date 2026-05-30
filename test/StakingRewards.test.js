const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("StakingRewards", function () {
  let stakingRewards, stakingToken, rewardToken;
  let owner, staker1, staker2;

  before(async function () {
    [owner, staker1, staker2] = await ethers.getSigners();

    const StakingToken = await ethers.getContractFactory("StakingToken");
    stakingToken = await StakingToken.deploy();
    await stakingToken.waitForDeployment();

    const RewardToken = await ethers.getContractFactory("RewardToken");
    rewardToken = await RewardToken.deploy();
    await rewardToken.waitForDeployment();

    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    stakingRewards = await StakingRewards.deploy(stakingToken.target, rewardToken.target);
    await stakingRewards.waitForDeployment();

    // Mint tokens for testing
    await stakingToken.mint(staker1.address, ethers.parseEther("1000"));
    await stakingToken.mint(staker2.address, ethers.parseEther("1000"));
    await rewardToken.mint(stakingRewards.target, ethers.parseEther("10000"));
    await stakingRewards.notifyRewardAmount(ethers.parseEther("1000"));
  });

  it("should allow staking tokens", async function () {
    const amount = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(stakingRewards.target, amount);
    await stakingRewards.connect(staker1).stake(amount);

    const staked = await stakingRewards.balanceOf(staker1.address);
    expect(staked).to.equal(amount);
  });

  it("should accrue rewards over time", async function () {
    const latestBlock = await ethers.provider.getBlock("latest");
    const nextTimestamp = latestBlock.timestamp + 3600;
    await ethers.provider.send("evm_setNextBlockTimestamp", [nextTimestamp]);
    await ethers.provider.send("evm_mine");

    const earned = await stakingRewards.earned(staker1.address);
    expect(earned).to.be.gt(0);
  });

  it("should allow withdrawal", async function () {
    const amount = ethers.parseEther("50");
    await stakingRewards.connect(staker1).withdraw(amount);

    const remaining = await stakingRewards.balanceOf(staker1.address);
    expect(remaining).to.equal(ethers.parseEther("50"));
  });

  it("should distribute rewards correctly to multiple stakers", async function () {
    const amount = ethers.parseEther("200");
    await stakingToken.connect(staker2).approve(stakingRewards.target, amount);
    await stakingRewards.connect(staker2).stake(amount);

    const latestBlock = await ethers.provider.getBlock("latest");
    const nextTimestamp = latestBlock.timestamp + 3600;
    await ethers.provider.send("evm_setNextBlockTimestamp", [nextTimestamp]);
    await ethers.provider.send("evm_mine");

    const earned1 = await stakingRewards.earned(staker1.address);
    const earned2 = await stakingRewards.earned(staker2.address);

    expect(earned2).to.be.gt(0);
    expect(earned1).to.be.gt(0);
  });
});
