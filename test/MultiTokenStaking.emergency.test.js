const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MultiTokenStaking emergencyWithdraw", function () {
  let staking, stakeToken, rewardToken;
  let owner, staker;

  beforeEach(async function () {
    [owner, staker] = await ethers.getSigners();
    const MockToken = await ethers.getContractFactory("MockERC20");
    stakeToken = await MockToken.deploy("Stake Token", "STK", ethers.utils.parseEther("1000000"));
    await stakeToken.deployed();
    rewardToken = await MockToken.deploy("Reward Token", "RWD", ethers.utils.parseEther("1000000"));
    await rewardToken.deployed();
    const MultiTokenStaking = await ethers.getContractFactory("MultiTokenStaking");
    staking = await MultiTokenStaking.deploy(rewardToken.address, ethers.utils.parseEther("1"));
    await staking.deployed();
    await staking.addPool(100, stakeToken.address);
    await rewardToken.transfer(staking.address, ethers.utils.parseEther("100000"));
  });

  describe("emergencyWithdraw", function () {
    beforeEach(async function () {
      await stakeToken.mint(staker.address, ethers.utils.parseEther("100"));
      await stakeToken.connect(staker).approve(staking.address, ethers.utils.parseEther("100"));
      await staking.connect(staker).deposit(0, ethers.utils.parseEther("100"));
    });

    it("should return all staked tokens to the user", async function () {
      const balBefore = await stakeToken.balanceOf(staker.address);
      await staking.connect(staker).emergencyWithdraw(0);
      const balAfter = await stakeToken.balanceOf(staker.address);
      expect(balAfter.sub(balBefore)).to.equal(ethers.utils.parseEther("100"));
    });

    it("should reset user amount and reward debt to zero", async function () {
      await staking.connect(staker).emergencyWithdraw(0);
      const user = await staking.userInfo(0, staker.address);
      expect(user.amount).to.equal(0);
      expect(user.rewardDebt).to.equal(0);
    });

    it("should decrement pool totalStaked", async function () {
      const poolBefore = await staking.poolInfo(0);
      await staking.connect(staker).emergencyWithdraw(0);
      const poolAfter = await staking.poolInfo(0);
      expect(poolAfter.totalStaked).to.equal(poolBefore.totalStaked.sub(ethers.utils.parseEther("100")));
    });

    it("should emit EmergencyWithdraw event", async function () {
      await expect(staking.connect(staker).emergencyWithdraw(0))
        .to.emit(staking, "EmergencyWithdraw")
        .withArgs(staker.address, 0, ethers.utils.parseEther("100"));
    });

    it("should NOT distribute rewards on emergency withdrawal", async function () {
      await ethers.provider.send("evm_increaseTime", [3600]);
      await ethers.provider.send("evm_mine");
      const rewardBefore = await rewardToken.balanceOf(staker.address);
      await staking.connect(staker).emergencyWithdraw(0);
      const rewardAfter = await rewardToken.balanceOf(staker.address);
      expect(rewardAfter).to.equal(rewardBefore);
    });

    it("should allow re-staking after emergency withdraw", async function () {
      await staking.connect(staker).emergencyWithdraw(0);
      await stakeToken.connect(staker).approve(staking.address, ethers.utils.parseEther("50"));
      await staking.connect(staker).deposit(0, ethers.utils.parseEther("50"));
      const user = await staking.userInfo(0, staker.address);
      expect(user.amount).to.equal(ethers.utils.parseEther("50"));
    });

    it("should revert if user has no staked tokens", async function () {
      await staking.connect(staker).emergencyWithdraw(0);
      await expect(staking.connect(staker).emergencyWithdraw(0))
        .to.be.revertedWith("MultiStaking: nothing to withdraw");
    });

    it("should allow multiple users to emergency withdraw independently", async function () {
      const [, , staker2] = await ethers.getSigners();
      await stakeToken.mint(staker2.address, ethers.utils.parseEther("200"));
      await stakeToken.connect(staker2).approve(staking.address, ethers.utils.parseEther("200"));
      await staking.connect(staker2).deposit(0, ethers.utils.parseEther("200"));
      await staking.connect(staker).emergencyWithdraw(0);
      await staking.connect(staker2).emergencyWithdraw(0);
      const user1 = await staking.userInfo(0, staker.address);
      const user2 = await staking.userInfo(0, staker2.address);
      expect(user1.amount).to.equal(0);
      expect(user2.amount).to.equal(0);
      const pool = await staking.poolInfo(0);
      expect(pool.totalStaked).to.equal(0);
    });
  });
});
