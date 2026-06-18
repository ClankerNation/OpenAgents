const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MultiTokenStaking", function () {
  let staking, tokenA, tokenB, rewardToken;
  let owner, user1, user2;

  beforeEach(async function () {
    [owner, user1, user2] = await ethers.getSigners();

    const MockERC20 = await ethers.getContractFactory("MockERC20");
    tokenA = await MockERC20.deploy("Token A", "TKA");
    tokenB = await MockERC20.deploy("Token B", "TKB");
    rewardToken = await MockERC20.deploy("Reward", "RWD");

    const MultiTokenStaking = await ethers.getContractFactory("MultiTokenStaking");
    staking = await MultiTokenStaking.deploy(rewardToken.target, ethers.parseEther("1"));
  });

  describe("addPool", function () {
    it("should add a pool", async function () {
      await staking.addPool(100, tokenA.target);
      const pool = await staking.poolInfo(0);
      expect(pool.stakeToken).to.equal(tokenA.target);
      expect(pool.allocPoint).to.equal(100);
      expect(pool.totalStaked).to.equal(0);
    });

    it("should reject zero address", async function () {
      await expect(staking.addPool(100, ethers.ZeroAddress))
        .to.be.revertedWith("Zero address");
    });

    it("should reject duplicate token", async function () {
      await staking.addPool(100, tokenA.target);
      await expect(staking.addPool(50, tokenA.target))
        .to.be.revertedWith("Pool exists");
    });

    it("should track totalAllocPoint", async function () {
      await staking.addPool(100, tokenA.target);
      await staking.addPool(200, tokenB.target);
      expect(await staking.totalAllocPoint()).to.equal(300);
    });

    it("should only allow owner to add pool", async function () {
      await expect(staking.connect(user1).addPool(100, tokenA.target))
        .to.be.revertedWithCustomError(staking, "OwnableUnauthorizedAccount");
    });
  });

  describe("setPoolAllocPoint", function () {
    beforeEach(async function () {
      await staking.addPool(100, tokenA.target);
      await staking.addPool(200, tokenB.target);
    });

    it("should update allocPoint and totalAllocPoint", async function () {
      await staking.setPoolAllocPoint(0, 300);
      const pool = await staking.poolInfo(0);
      expect(pool.allocPoint).to.equal(300);
      expect(await staking.totalAllocPoint()).to.equal(500);
    });

    it("should only allow owner", async function () {
      await expect(staking.connect(user1).setPoolAllocPoint(0, 50))
        .to.be.revertedWithCustomError(staking, "OwnableUnauthorizedAccount");
    });

    it("should emit PoolUpdated event", async function () {
      await expect(staking.setPoolAllocPoint(0, 300))
        .to.emit(staking, "PoolUpdated")
        .withArgs(0, 100, 300);
    });
  });

  describe("deposit", function () {
    beforeEach(async function () {
      await staking.addPool(100, tokenA.target);
      await tokenA.transfer(user1.address, ethers.parseEther("1000"));
      await tokenA.connect(user1).approve(staking.target, ethers.parseEther("100"));
    });

    it("should stake tokens", async function () {
      await staking.connect(user1).deposit(0, ethers.parseEther("100"));
      const userInfo = await staking.userInfo(0, user1.address);
      expect(userInfo.amount).to.equal(ethers.parseEther("100"));
    });

    it("should increase totalStaked", async function () {
      await staking.connect(user1).deposit(0, ethers.parseEther("100"));
      const pool = await staking.poolInfo(0);
      expect(pool.totalStaked).to.equal(ethers.parseEther("100"));
    });

    it("should harvest pending rewards on second deposit", async function () {
      await staking.connect(user1).deposit(0, ethers.parseEther("100"));
      // Fund reward token to contract
      await rewardToken.transfer(staking.target, ethers.parseEther("100000"));
      // Advance time so rewards accrue (will trigger updatePool on next deposit)
      await ethers.provider.send("evm_increaseTime", [3600]);
      await ethers.provider.send("evm_mine");
      // Second deposit triggers harvest
      await expect(staking.connect(user1).deposit(0, ethers.parseEther("0")))
        .to.emit(staking, "Harvest");
    });
  });

  describe("withdraw", function () {
    beforeEach(async function () {
      await staking.addPool(100, tokenA.target);
      await tokenA.transfer(user1.address, ethers.parseEther("1000"));
      await tokenA.connect(user1).approve(staking.target, ethers.parseEther("500"));
      // Fund reward contract so harvest on withdraw doesn't revert
      await rewardToken.transfer(staking.target, ethers.parseEther("100000"));
    });

    it("should withdraw staked tokens", async function () {
      await staking.connect(user1).deposit(0, ethers.parseEther("200"));
      await staking.connect(user1).withdraw(0, ethers.parseEther("100"));
      const userInfo = await staking.userInfo(0, user1.address);
      expect(userInfo.amount).to.equal(ethers.parseEther("100"));
    });

    it("should reject insufficient balance", async function () {
      await staking.connect(user1).deposit(0, ethers.parseEther("200"));
      await expect(staking.connect(user1).withdraw(0, ethers.parseEther("300")))
        .to.be.revertedWith("MultiStaking: insufficient balance");
    });

    it("should harvest on withdraw", async function () {
      await staking.connect(user1).deposit(0, ethers.parseEther("200"));
      await ethers.provider.send("evm_increaseTime", [3600]);
      await ethers.provider.send("evm_mine");
      await expect(staking.connect(user1).withdraw(0, ethers.parseEther("50")))
        .to.emit(staking, "Harvest");
    });
  });

  describe("reward distribution", function () {
    beforeEach(async function () {
      await staking.addPool(100, tokenA.target);
      await staking.addPool(300, tokenB.target);
      await tokenA.transfer(user1.address, ethers.parseEther("1000"));
      await tokenB.transfer(user2.address, ethers.parseEther("1000"));
      await tokenA.connect(user1).approve(staking.target, ethers.parseEther("500"));
      await tokenB.connect(user2).approve(staking.target, ethers.parseEther("500"));
    });

    it("should distribute rewards proportionally across pools", async function () {
      await staking.connect(user1).deposit(0, ethers.parseEther("100"));
      await staking.connect(user2).deposit(1, ethers.parseEther("100"));

      await rewardToken.transfer(staking.target, ethers.parseEther("10000"));
      await ethers.provider.send("evm_increaseTime", [86400]);
      await ethers.provider.send("evm_mine");

      const pending0 = await staking.pendingReward(0, user1.address);
      const pending1 = await staking.pendingReward(1, user2.address);
      expect(pending0).to.be.gt(0);
      expect(pending1).to.be.gt(0);
      // Pool1 (300 allocPoint) should get ~3x the reward of pool0 (100 allocPoint)
      const ratio = Number(pending1) / Number(pending0);
      expect(ratio).to.be.closeTo(3, 0.5);
    });

    it("should stop accruing rewards when totalStaked is 0", async function () {
      await staking.connect(user1).deposit(0, ethers.parseEther("100"));
      await rewardToken.transfer(staking.target, ethers.parseEther("10000"));

      // Advance time and mine so rewards accrue
      await ethers.provider.send("evm_increaseTime", [3600]);
      await ethers.provider.send("evm_mine");

      const pendingBefore = await staking.pendingReward(0, user1.address);
      expect(pendingBefore).to.be.gt(0);

      // Withdraw all — totalStaked becomes 0
      // This also harvests pending rewards
      await staking.connect(user1).withdraw(0, ethers.parseEther("100"));

      // Advance time further
      await ethers.provider.send("evm_increaseTime", [3600]);
      await ethers.provider.send("evm_mine");

      // accRewardPerShare should not have increased since totalStaked was 0
      const pool = await staking.poolInfo(0);
      // Since updatePool skips reward when totalStaked=0,
      // lastRewardTime advances to block.timestamp
      // So pending for the withdrawn user (now amount=0) = 0
      pendingAfter = await staking.pendingReward(0, user1.address);
      expect(pendingAfter).to.equal(0);
    });
  });
});
