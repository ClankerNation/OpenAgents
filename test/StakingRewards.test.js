const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("StakingRewards", function () {
  let stakingRewards, stakingToken, rewardToken;
  let owner, staker1, staker2;

  beforeEach(async function () {
    [owner, staker1, staker2] = await ethers.getSigners();

    const StakingToken = await ethers.getContractFactory("StakingToken");
    stakingToken = await StakingToken.deploy();
    await stakingToken.waitForDeployment();

    const RewardToken = await ethers.getContractFactory("RewardToken");
    rewardToken = await RewardToken.deploy();
    await rewardToken.waitForDeployment();

    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    stakingRewards = await StakingRewards.deploy(
      await stakingToken.getAddress(),
      await rewardToken.getAddress()
    );
    await stakingRewards.waitForDeployment();

    // Mint tokens for testing
    await stakingToken.mint(staker1.address, ethers.parseEther("1000"));
    await stakingToken.mint(staker2.address, ethers.parseEther("1000"));
    await rewardToken.mint(await stakingRewards.getAddress(), ethers.parseEther("10000"));
    await stakingRewards.notifyRewardAmount(ethers.parseEther("700"));
  });

  it("should allow staking tokens", async function () {
    const amount = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(await stakingRewards.getAddress(), amount);
    await stakingRewards.connect(staker1).stake(amount);

    const staked = await stakingRewards.balanceOf(staker1.address);
    expect(staked).to.equal(amount);
  });

  it("should accrue rewards over time", async function () {
    const amount = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(await stakingRewards.getAddress(), amount);
    await stakingRewards.connect(staker1).stake(amount);

    await ethers.provider.send("evm_increaseTime", [24 * 60 * 60]);
    await ethers.provider.send("evm_mine");

    const earned = await stakingRewards.earned(staker1.address);
    expect(earned).to.be.gt(0);
  });

  it("should allow withdrawal", async function () {
    const stakedAmount = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(await stakingRewards.getAddress(), stakedAmount);
    await stakingRewards.connect(staker1).stake(stakedAmount);

    const withdrawAmount = ethers.parseEther("50");
    await stakingRewards.connect(staker1).withdraw(withdrawAmount);

    const remaining = await stakingRewards.balanceOf(staker1.address);
    expect(remaining).to.equal(ethers.parseEther("50"));
  });

  it("should distribute rewards correctly to multiple stakers", async function () {
    const amount1 = ethers.parseEther("100");
    const amount2 = ethers.parseEther("200");
    await stakingToken.connect(staker1).approve(await stakingRewards.getAddress(), amount1);
    await stakingToken.connect(staker2).approve(await stakingRewards.getAddress(), amount2);
    await stakingRewards.connect(staker1).stake(amount1);
    await stakingRewards.connect(staker2).stake(amount2);

    await ethers.provider.send("evm_increaseTime", [24 * 60 * 60]);
    await ethers.provider.send("evm_mine");

    const earned1 = await stakingRewards.earned(staker1.address);
    const earned2 = await stakingRewards.earned(staker2.address);

    // staker2 staked 2x more, so should earn proportionally more.
    expect(earned2).to.be.gt(0);
    expect(earned2).to.be.gt(earned1);
  });
});
