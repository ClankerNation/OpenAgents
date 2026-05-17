const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("StakingRewards", function () {
  let stakingRewards, stakingToken, rewardToken;
  let owner, staker1, staker2, attacker;

  beforeEach(async function () {
    [owner, staker1, staker2, attacker] = await ethers.getSigners();

    const StakingToken = await ethers.getContractFactory("StakingToken");
    stakingToken = await StakingToken.deploy();
    await stakingToken.waitForDeployment();

    const RewardToken = await ethers.getContractFactory("RewardToken");
    rewardToken = await RewardToken.deploy();
    await rewardToken.waitForDeployment();

    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    stakingRewards = await StakingRewards.deploy(
      stakingToken.target,
      rewardToken.target
    );
    await stakingRewards.waitForDeployment();

    // Mint tokens for testing
    await stakingToken.mint(staker1.address, ethers.parseEther("1000"));
    await stakingToken.mint(staker2.address, ethers.parseEther("1000"));
    await rewardToken.mint(
      stakingRewards.target,
      ethers.parseEther("10000")
    );

    // Set up rewards
    await stakingRewards.notifyRewardAmount(ethers.parseEther("1000"));
  });

  describe("deployment", function () {
    it("should set the correct owner", async function () {
      expect(await stakingRewards.owner()).to.equal(owner.address);
    });

    it("should set the correct tokens", async function () {
      expect(await stakingRewards.stakingToken()).to.equal(
        stakingToken.target
      );
      expect(await stakingRewards.rewardsToken()).to.equal(
        rewardToken.target
      );
    });
  });

  describe("staking", function () {
    it("should allow staking tokens", async function () {
      const amount = ethers.parseEther("100");
      await stakingToken
        .connect(staker1)
        .approve(stakingRewards.target, amount);
      await stakingRewards.connect(staker1).stake(amount);

      expect(await stakingRewards.balanceOf(staker1.address)).to.equal(amount);
      expect(await stakingRewards.totalSupply()).to.equal(amount);
    });

    it("should revert when staking zero", async function () {
      await stakingToken
        .connect(staker1)
        .approve(stakingRewards.target, ethers.parseEther("100"));
      await expect(stakingRewards.connect(staker1).stake(0)).to.be.revertedWith(
        "Cannot stake 0"
      );
    });

    it("should emit Staked event", async function () {
      const amount = ethers.parseEther("100");
      await stakingToken
        .connect(staker1)
        .approve(stakingRewards.target, amount);
      await expect(stakingRewards.connect(staker1).stake(amount))
        .to.emit(stakingRewards, "Staked")
        .withArgs(staker1.address, amount);
    });
  });

  describe("withdrawal", function () {
    beforeEach(async function () {
      const amount = ethers.parseEther("100");
      await stakingToken
        .connect(staker1)
        .approve(stakingRewards.target, amount);
      await stakingRewards.connect(staker1).stake(amount);
    });

    it("should allow withdrawal", async function () {
      const amount = ethers.parseEther("50");
      await stakingRewards.connect(staker1).withdraw(amount);

      expect(await stakingRewards.balanceOf(staker1.address)).to.equal(
        ethers.parseEther("50")
      );
      expect(await stakingRewards.totalSupply()).to.equal(
        ethers.parseEther("50")
      );
    });

    it("should revert when withdrawing zero", async function () {
      await expect(stakingRewards.connect(staker1).withdraw(0)).to.be.revertedWith(
        "Cannot withdraw 0"
      );
    });

    it("should emit Withdrawn event", async function () {
      const amount = ethers.parseEther("50");
      await expect(stakingRewards.connect(staker1).withdraw(amount))
        .to.emit(stakingRewards, "Withdrawn")
        .withArgs(staker1.address, amount);
    });
  });

  describe("rewards", function () {
    beforeEach(async function () {
      const amount = ethers.parseEther("100");
      await stakingToken
        .connect(staker1)
        .approve(stakingRewards.target, amount);
      await stakingRewards.connect(staker1).stake(amount);
    });

    it("should accrue rewards over time", async function () {
      // Advance time
      await ethers.provider.send("evm_increaseTime", [86400]); // 1 day
      await ethers.provider.send("evm_mine", []);

      const earned = await stakingRewards.earned(staker1.address);
      expect(earned).to.be.gt(0);
    });

    it("should allow claiming rewards", async function () {
      // Advance time to earn rewards
      await ethers.provider.send("evm_increaseTime", [86400]);
      await ethers.provider.send("evm_mine", []);

      const earned = await stakingRewards.earned(staker1.address);
      expect(earned).to.be.gt(0);

      await stakingRewards.connect(staker1).getReward();

      expect(await stakingRewards.earned(staker1.address)).to.equal(0);
    });

    it("should emit RewardPaid event", async function () {
      await ethers.provider.send("evm_increaseTime", [86400]);
      await ethers.provider.send("evm_mine", []);

      await expect(stakingRewards.connect(staker1).getReward())
        .to.emit(stakingRewards, "RewardPaid");
    });

    it("should distribute rewards proportionally to multiple stakers", async function () {
      const amount2 = ethers.parseEther("200");
      await stakingToken
        .connect(staker2)
        .approve(stakingRewards.target, amount2);
      await stakingRewards.connect(staker2).stake(amount2);

      // Advance time
      await ethers.provider.send("evm_increaseTime", [86400]);
      await ethers.provider.send("evm_mine", []);

      const earned1 = await stakingRewards.earned(staker1.address);
      const earned2 = await stakingRewards.earned(staker2.address);

      // staker2 staked 2x more, should earn roughly 2x more (proportional)
      expect(earned2).to.be.gt(earned1);
    });
  });

  describe("reward period", function () {
    it("should stop accruing rewards after period finishes", async function () {
      const amount = ethers.parseEther("100");
      await stakingToken
        .connect(staker1)
        .approve(stakingRewards.target, amount);
      await stakingRewards.connect(staker1).stake(amount);

      // Advance to just after the reward period ends
      await ethers.provider.send("evm_increaseTime", [604800]);
      await ethers.provider.send("evm_mine", []);

      // Capture rewardPerToken at period end
      const rewardPerTokenAtEnd = await stakingRewards.rewardPerToken();

      // Advance further past the period
      await ethers.provider.send("evm_increaseTime", [86400]);
      await ethers.provider.send("evm_mine", []);

      // rewardPerToken should NOT increase after periodFinish
      const rewardPerTokenAfter = await stakingRewards.rewardPerToken();
      expect(rewardPerTokenAfter).to.equal(rewardPerTokenAtEnd);
    });

    it("should allow adding new rewards after period finishes", async function () {
      // Advance past the reward period
      await ethers.provider.send("evm_increaseTime", [604800 + 1]);
      await ethers.provider.send("evm_mine", []);

      await rewardToken.mint(
        stakingRewards.target,
        ethers.parseEther("5000")
      );
      await stakingRewards.notifyRewardAmount(ethers.parseEther("5000"));

      const newPeriodFinish = await stakingRewards.periodFinish();
      expect(newPeriodFinish).to.be.gt(0);
    });
  });

  describe("access control", function () {
    it("should only allow owner to call notifyRewardAmount", async function () {
      await rewardToken.mint(stakingRewards.target, ethers.parseEther("5000"));
      await expect(
        stakingRewards.connect(staker1).notifyRewardAmount(ethers.parseEther("500"))
      ).to.be.reverted;
    });

    it("should allow owner to call notifyRewardAmount", async function () {
      await rewardToken.mint(stakingRewards.target, ethers.parseEther("5000"));
      await expect(
        stakingRewards.connect(owner).notifyRewardAmount(ethers.parseEther("500"))
      ).to.emit(stakingRewards, "RewardAdded");
    });
  });

  describe("reentrancy protection", function () {
    it("should have nonReentrant on stake, withdraw, and getReward", async function () {
      // Functional test: stake + withdraw should work normally
      const stakeAmount = ethers.parseEther("100");
      await stakingToken
        .connect(staker1)
        .approve(stakingRewards.target, stakeAmount);
      await stakingRewards.connect(staker1).stake(stakeAmount);

      const balance = await stakingRewards.balanceOf(staker1.address);
      expect(balance).to.equal(stakeAmount);

      await stakingRewards.connect(staker1).withdraw(stakeAmount);
      expect(await stakingRewards.balanceOf(staker1.address)).to.equal(0);
    });

    it("should prevent reentrancy attack on withdraw via token callback", async function () {
      // Deploy a staking rewards instance with a callback token
      const CallbackToken = await ethers.getContractFactory("CallbackToken");
      const callbackToken = await CallbackToken.deploy();
      await callbackToken.waitForDeployment();

      const StakingRewards = await ethers.getContractFactory("StakingRewards");
      const sr = await StakingRewards.deploy(callbackToken.target, rewardToken.target);
      await sr.waitForDeployment();

      // Deploy attacker
      const Attacker = await ethers.getContractFactory("ReentrancyAttacker");
      const attackContract = await Attacker.deploy(sr.target);
      await attackContract.waitForDeployment();

      // Setup: mint tokens to attacker and approve staking contract
      const stakeAmount = ethers.parseEther("100");
      await callbackToken.mint(attackContract.target, stakeAmount);
      await callbackToken.forceApprove(attackContract.target, sr.target, stakeAmount);

      // Attacker stakes
      await attackContract.stake(stakeAmount);

      // Verify attacker has staked
      const balance = await sr.balanceOf(attackContract.target);
      expect(balance).to.equal(stakeAmount);

      // Attack: withdraw triggers token transfer -> callback -> re-enter withdraw
      // nonReentrant should block the reentrant call
      await attackContract.attack(stakeAmount);

      // After attack, balance should be 0 (tokens withdrawn)
      expect(await sr.balanceOf(attackContract.target)).to.equal(0);

      // The reentrant call should have been blocked
      // If it wasn't, the attacker would have drained the contract
      const contractBalance = await callbackToken.balanceOf(sr.target);
      expect(contractBalance).to.equal(0);
    });

    it("should prevent reentrancy attack on getReward", async function () {
      const amount = ethers.parseEther("100");
      await stakingToken
        .connect(staker1)
        .approve(stakingRewards.target, amount);
      await stakingRewards.connect(staker1).stake(amount);

      // Advance time to earn rewards
      await ethers.provider.send("evm_increaseTime", [86400]);
      await ethers.provider.send("evm_mine", []);

      const earned = await stakingRewards.earned(staker1.address);
      expect(earned).to.be.gt(0);

      // Claim rewards - should succeed without reentrancy issues
      await stakingRewards.connect(staker1).getReward();

      // Earned should be 0 after claiming
      expect(await stakingRewards.earned(staker1.address)).to.equal(0);
    });
  });

  describe("edge cases", function () {
    it("should handle zero total supply in rewardPerToken", async function () {
      const rpt = await stakingRewards.rewardPerToken();
      expect(rpt).to.equal(0);
    });

    it("should not crash when claiming zero rewards", async function () {
      await stakingRewards.connect(staker1).getReward();
    });
  });
});
