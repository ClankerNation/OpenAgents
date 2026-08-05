const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("StakingRewards issue #7", function () {
  let stakingRewards;
  let stakingToken;
  let rewardToken;
  let owner;
  let distributor;
  let staker;
  let attacker;

  const STAKE_AMOUNT = ethers.parseEther("100");

  beforeEach(async function () {
    [owner, distributor, staker, attacker] = await ethers.getSigners();

    const TestToken = await ethers.getContractFactory("StakingRewardsTestToken");
    stakingToken = await TestToken.deploy("Stake Token", "STK");
    rewardToken = await TestToken.deploy("Reward Token", "RWD");
    await stakingToken.waitForDeployment();
    await rewardToken.waitForDeployment();

    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    stakingRewards = await StakingRewards.deploy(
      await stakingToken.getAddress(),
      await rewardToken.getAddress()
    );
    await stakingRewards.waitForDeployment();

    await stakingRewards.setRewardsDistributor(distributor.address);
    await stakingToken.mint(staker.address, STAKE_AMOUNT);
    await rewardToken.mint(await stakingRewards.getAddress(), ethers.parseEther("1000000"));
    await stakingToken.connect(staker).approve(await stakingRewards.getAddress(), STAKE_AMOUNT);
    await stakingRewards.connect(staker).stake(STAKE_AMOUNT);
  });

  it("does not accrue additional rewards after periodFinish", async function () {
    const reward = ethers.parseEther("700");
    await stakingRewards.connect(distributor).notifyRewardAmount(reward);

    const duration = await stakingRewards.rewardsDuration();
    await time.increase(Number(duration) + 1);
    const earnedAtFinish = await stakingRewards.earned(staker.address);

    await time.increase(3 * 24 * 60 * 60);
    const earnedAfterFinish = await stakingRewards.earned(staker.address);

    expect(earnedAfterFinish).to.equal(earnedAtFinish);
  });

  it("only allows the configured rewards distributor to notify rewards", async function () {
    await expect(
      stakingRewards.connect(attacker).notifyRewardAmount(ethers.parseEther("1"))
    ).to.be.revertedWith("StakingRewards: not distributor");

    await expect(
      stakingRewards.connect(distributor).notifyRewardAmount(ethers.parseEther("1"))
    ).to.emit(stakingRewards, "RewardAdded");
  });

  it("keeps precision loss below 0.01 percent for small rewards", async function () {
    const reward = 500000n;
    await stakingRewards.connect(distributor).notifyRewardAmount(reward);

    const duration = await stakingRewards.rewardsDuration();
    await time.increase(Number(duration) + 1);

    const earned = await stakingRewards.earned(staker.address);
    const loss = reward - earned;
    const maxLoss = reward / 10000n;

    expect(loss).to.be.lte(maxLoss);
  });
});
