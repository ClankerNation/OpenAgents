const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("StakingRewards - Phantom Reward Fix", function () {
  let stakingRewards, stakingToken, rewardToken;
  let owner, staker1, staker2, attacker;

  const REWARD_AMOUNT = ethers.utils.parseEther("1000");
  const STAKE_AMOUNT = ethers.utils.parseEther("100");
  const SEVEN_DAYS = 7 * 24 * 60 * 60;

  beforeEach(async function () {
    [owner, staker1, staker2, attacker] = await ethers.getSigners();

    const MockERC20 = await ethers.getContractFactory("MockERC20");
    stakingToken = await MockERC20.deploy("Staking Token", "STK");
    await stakingToken.deployed();
    rewardToken = await MockERC20.deploy("Reward Token", "RWD");
    await rewardToken.deployed();

    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    stakingRewards = await StakingRewards.deploy(stakingToken.address, rewardToken.address);
    await stakingRewards.deployed();

    await stakingToken.mint(staker1.address, ethers.utils.parseEther("10000"));
    await stakingToken.mint(staker2.address, ethers.utils.parseEther("10000"));
    await rewardToken.mint(owner.address, ethers.utils.parseEther("100000"));

    await stakingToken.connect(staker1).approve(stakingRewards.address, ethers.utils.parseEther("10000"));
    await stakingToken.connect(staker2).approve(stakingRewards.address, ethers.utils.parseEther("10000"));
  });

  describe("Phantom reward accrual after period expiry", function () {
    it("should not accrue rewards after periodFinish", async function () {
      await rewardToken.approve(stakingRewards.address, REWARD_AMOUNT);
      await stakingRewards.notifyRewardAmount(REWARD_AMOUNT);
      await stakingRewards.connect(staker1).stake(STAKE_AMOUNT);

      await time.increase(SEVEN_DAYS);
      const earnedAtEnd = await stakingRewards.earned(staker1.address);

      await time.increase(SEVEN_DAYS);
      const earnedAfterExpiry = await stakingRewards.earned(staker1.address);

      expect(earnedAfterExpiry).to.be.lte(earnedAtEnd.add(1));
    });

    it("rewardPerToken should freeze after periodFinish", async function () {
      await rewardToken.approve(stakingRewards.address, REWARD_AMOUNT);
      await stakingRewards.notifyRewardAmount(REWARD_AMOUNT);
      await stakingRewards.connect(staker1).stake(STAKE_AMOUNT);

      await time.increase(SEVEN_DAYS + 1000);
      const rpt = await stakingRewards.rewardPerToken();

      await time.increase(SEVEN_DAYS);
      const rptLater = await stakingRewards.rewardPerToken();

      expect(rptLater.sub(rpt)).to.be.lte(1);
    });

    it("lastTimeRewardApplicable should return periodFinish after expiry", async function () {
      await rewardToken.approve(stakingRewards.address, REWARD_AMOUNT);
      await stakingRewards.notifyRewardAmount(REWARD_AMOUNT);

      const periodFinish = await stakingRewards.periodFinish();
      const beforeExpiry = await stakingRewards.lastTimeRewardApplicable();
      expect(beforeExpiry).to.be.lt(periodFinish);

      await time.increaseTo(periodFinish.add(1000));
      const afterExpiry = await stakingRewards.lastTimeRewardApplicable();
      expect(afterExpiry).to.equal(periodFinish);
    });
  });

  describe("Access control on notifyRewardAmount", function () {
    it("should revert when non-owner calls notifyRewardAmount", async function () {
      await expect(
        stakingRewards.connect(attacker).notifyRewardAmount(ethers.utils.parseEther("100"))
      ).to.be.revertedWithCustomError(stakingRewards, "OwnableUnauthorizedAccount");
    });

    it("should allow owner to call notifyRewardAmount", async function () {
      await rewardToken.approve(stakingRewards.address, REWARD_AMOUNT);
      await expect(
        stakingRewards.notifyRewardAmount(REWARD_AMOUNT)
      ).to.not.be.reverted;
    });
  });

  describe("Precision loss fix", function () {
    it("should not lose all rewards for small reward amounts", async function () {
      const smallReward = 500000;
      await rewardToken.mint(stakingRewards.address, smallReward);

      await stakingRewards.connect(staker1).stake(STAKE_AMOUNT);
      await stakingRewards.notifyRewardAmount(smallReward);

      const rate = await stakingRewards.rewardRate();
      expect(rate).to.be.gt(0);

      await time.increase(3600);
      const earned = await stakingRewards.earned(staker1.address);
      expect(earned).to.be.gt(0);
    });

    it("precision loss should be less than 0.01pct for normal reward amounts", async function () {
      const reward = ethers.utils.parseEther("1000");
      await rewardToken.approve(stakingRewards.address, reward);

      await stakingRewards.connect(staker1).stake(STAKE_AMOUNT);
      await stakingRewards.notifyRewardAmount(reward);

      await time.increase(SEVEN_DAYS);
      const earned = await stakingRewards.earned(staker1.address);

      const tolerance = reward.mul(1).div(10000);
      expect(earned).to.be.gte(reward.sub(tolerance));
    });
  });

  describe("Normal staking behavior", function () {
    it("should still allow staking, earning, and withdrawing normally", async function () {
      await rewardToken.approve(stakingRewards.address, REWARD_AMOUNT.mul(2));
      await stakingRewards.notifyRewardAmount(REWARD_AMOUNT.mul(2));

      await stakingRewards.connect(staker1).stake(STAKE_AMOUNT);
      await stakingRewards.connect(staker2).stake(STAKE_AMOUNT.mul(2));

      await time.increase(SEVEN_DAYS);

      const earned1 = await stakingRewards.earned(staker1.address);
      const earned2 = await stakingRewards.earned(staker2.address);

      expect(earned1).to.be.gt(0);
      expect(earned2).to.be.gt(0);
      expect(earned2).to.be.gt(earned1);
    });

    it("should allow getReward and withdrawal after period ends", async function () {
      await rewardToken.approve(stakingRewards.address, REWARD_AMOUNT);
      await stakingRewards.notifyRewardAmount(REWARD_AMOUNT);

      await stakingRewards.connect(staker1).stake(STAKE_AMOUNT);

      await time.increase(SEVEN_DAYS + 100);
      await stakingRewards.connect(staker1).getReward();

      const earned = await stakingRewards.earned(staker1.address);
      expect(earned).to.equal(0);

      await stakingRewards.connect(staker1).withdraw(STAKE_AMOUNT);
      const balance = await stakingRewards.balanceOf(staker1.address);
      expect(balance).to.equal(0);
    });
  });
});
