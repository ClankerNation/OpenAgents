const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("StakingRewards", function () {
  let stakingToken, rewardsToken, staking;
  let owner, user1, user2, attacker;
  const REWARDS_DURATION = 7 * 24 * 60 * 60; // 7 days
  const ONE_DAY = 24 * 60 * 60;
  const ONE_TOKEN = ethers.parseEther("1");

  beforeEach(async function () {
    [owner, user1, user2, attacker] = await ethers.getSigners();

    const MockERC20 = await ethers.getContractFactory("MockERC20");
    stakingToken = await MockERC20.deploy("Staking Token", "STK");
    rewardsToken = await MockERC20.deploy("Reward Token", "RWD");

    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    staking = await StakingRewards.deploy(stakingToken.target, rewardsToken.target);
    await staking.waitForDeployment();

    // Transfer from deployer (owner) to test users and fund staking contract with rewards
    for (const user of [user1, user2]) {
      await stakingToken.transfer(user.address, ONE_TOKEN * 1000n);
      await stakingToken.connect(user).approve(staking.target, ONE_TOKEN * 1000n);
    }
    await stakingToken.connect(owner).approve(staking.target, ONE_TOKEN * 1000n);
    // Pre-fund the staking contract with reward tokens before notifyRewardAmount
    await rewardsToken.transfer(staking.target, ONE_TOKEN * 10000n);
  });

  describe("notifyRewardAmount", function () {
    it("should only allow owner to notify rewards", async function () {
      await expect(
        staking.connect(attacker).notifyRewardAmount(ONE_TOKEN * 100n)
      ).to.be.revertedWith("Not owner");
    });

    it("should reject reward too small for duration", async function () {
      const tooSmall = 500_000; // less than rewardsDuration (604800), so rate = 0
      await expect(
        staking.connect(owner).notifyRewardAmount(tooSmall)
      ).to.be.revertedWith("Reward too small for duration");
    });

    it("should set reward rate and period finish", async function () {
      const reward = ONE_TOKEN * 100n;
      await staking.connect(owner).notifyRewardAmount(reward);

      const rate = await staking.rewardRate();
      expect(rate).to.equal(reward / BigInt(REWARDS_DURATION));

      const finish = await staking.periodFinish();
      const block = await ethers.provider.getBlock("latest");
      expect(finish).to.equal(block.timestamp + REWARDS_DURATION);
    });

    it("should extend remaining when called mid-period", async function () {
      await staking.connect(owner).notifyRewardAmount(ONE_TOKEN * 100n);

      await ethers.provider.send("evm_increaseTime", [ONE_DAY]);
      await ethers.provider.send("evm_mine", []);

      await staking.connect(owner).notifyRewardAmount(ONE_TOKEN * 50n);

      const rate = await staking.rewardRate();
      expect(rate).to.be.gt(0n);
    });
  });

  describe("phantom rewards", function () {
    it("should stop accruing after periodFinish", async function () {
      await staking.connect(owner).notifyRewardAmount(ONE_TOKEN * 100n);
      await staking.connect(user1).stake(ONE_TOKEN * 10n);

      // Fast-forward past periodFinish
      await ethers.provider.send("evm_increaseTime", [REWARDS_DURATION + ONE_DAY]);
      await ethers.provider.send("evm_mine", []);

      const earned1 = await staking.earned(user1.address);

      // Fast-forward another week - should NOT increase (phantom rewards fixed)
      await ethers.provider.send("evm_increaseTime", [REWARDS_DURATION]);
      await ethers.provider.send("evm_mine", []);

      const earned2 = await staking.earned(user1.address);
      expect(earned2).to.equal(earned1);
    });

    it("should not allow claiming more than the reward pool", async function () {
      const reward = ONE_TOKEN * 10n;
      await staking.connect(owner).notifyRewardAmount(reward);
      await staking.connect(user1).stake(ONE_TOKEN * 100n);

      await ethers.provider.send("evm_increaseTime", [REWARDS_DURATION + ONE_DAY]);
      await ethers.provider.send("evm_mine", []);

      await staking.connect(user1).getReward();

      const claimed = await rewardsToken.balanceOf(user1.address);
      expect(claimed).to.be.at.most(reward);
    });
  });

  describe("staking lifecycle", function () {
    beforeEach(async function () {
      await staking.connect(owner).notifyRewardAmount(ONE_TOKEN * 100n);
    });

    it("should stake and track balance", async function () {
      await staking.connect(user1).stake(ONE_TOKEN * 10n);
      expect(await staking.balanceOf(user1.address)).to.equal(ONE_TOKEN * 10n);
      expect(await staking.totalSupply()).to.equal(ONE_TOKEN * 10n);
    });

    it("should reject zero staking", async function () {
      await expect(staking.connect(user1).stake(0)).to.be.revertedWith("Cannot stake 0");
    });

    it("should allow partial withdrawal", async function () {
      await staking.connect(user1).stake(ONE_TOKEN * 10n);
      await staking.connect(user1).withdraw(ONE_TOKEN * 4n);
      expect(await staking.balanceOf(user1.address)).to.equal(ONE_TOKEN * 6n);
    });

    it("should reject zero withdrawal", async function () {
      await staking.connect(user1).stake(ONE_TOKEN * 10n);
      await expect(staking.connect(user1).withdraw(0)).to.be.revertedWith("Cannot withdraw 0");
    });

    it("should distribute rewards proportionally", async function () {
      await staking.connect(user1).stake(ONE_TOKEN * 30n); // 30%
      await staking.connect(user2).stake(ONE_TOKEN * 70n); // 70%

      await ethers.provider.send("evm_increaseTime", [REWARDS_DURATION - 100]);
      await ethers.provider.send("evm_mine", []);

      await staking.connect(user1).getReward();
      await staking.connect(user2).getReward();

      const bal1 = await rewardsToken.balanceOf(user1.address);
      const bal2 = await rewardsToken.balanceOf(user2.address);
      const total = bal1 + bal2;

      // Within 1% tolerance for rounding
      expect(bal1 * 100n / total).to.be.closeTo(30n, 1n);
      expect(bal2 * 100n / total).to.be.closeTo(70n, 1n);
    });

    it("should reset reward to zero after claim", async function () {
      await staking.connect(user1).stake(ONE_TOKEN * 10n);

      await ethers.provider.send("evm_increaseTime", [ONE_DAY]);
      await ethers.provider.send("evm_mine", []);

      await staking.connect(user1).getReward();
      expect(await staking.rewards(user1.address)).to.equal(0);
    });

    it("should allow multiple reward cycles", async function () {
      await staking.connect(user1).stake(ONE_TOKEN * 10n);

      // Cycle 1
      await ethers.provider.send("evm_increaseTime", [ONE_DAY]);
      await ethers.provider.send("evm_mine", []);
      await staking.connect(user1).getReward();
      const claim1 = await rewardsToken.balanceOf(user1.address);
      expect(claim1).to.be.gt(0n);

      // Cycle 2 with new rewards
      await staking.connect(owner).notifyRewardAmount(ONE_TOKEN * 100n);
      await ethers.provider.send("evm_increaseTime", [ONE_DAY]);
      await ethers.provider.send("evm_mine", []);
      await staking.connect(user1).getReward();
      const claim2 = await rewardsToken.balanceOf(user1.address);
      expect(claim2).to.be.gt(claim1);
    });
  });
});
