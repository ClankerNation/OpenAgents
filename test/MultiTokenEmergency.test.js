// @contributor: Claude Code (Claude Opus 4.7)
// @platform-config: Task: Write emergencyWithdraw tests — revert when nothing staked, returns all tokens, resets state, decrements totalStaked, no rewards, correct event emission. Rules: Use ethers v6, hardhat-toolbox, chai assertions. Tools: npx hardhat test. Style: JS/Node/ethers conventions.
// @env: os=linux, arch=x86_64, home_dir=/home/michael, working_dir=/home/michael/web3-community/OpenAgents, shell=bash
// @timestamp: 2026-06-20T08:00:00Z
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MultiTokenStaking - EmergencyWithdraw", function () {
  let staking, tokenA, rewardToken;
  let owner, user1;

  beforeEach(async function () {
    [owner, user1] = await ethers.getSigners();

    const MockERC20 = await ethers.getContractFactory("MockERC20");
    tokenA = await MockERC20.deploy("Token A", "TKA");
    rewardToken = await MockERC20.deploy("Reward", "RWD");

    const MultiTokenStaking = await ethers.getContractFactory("MultiTokenStaking");
    staking = await MultiTokenStaking.deploy(rewardToken.target, ethers.parseEther("1"));
    await staking.addPool(100, tokenA.target);
    await tokenA.transfer(user1.address, ethers.parseEther("1000"));
    await tokenA.connect(user1).approve(staking.target, ethers.parseEther("500"));
  });

  it("should revert if nothing staked", async function () {
    await expect(staking.connect(user1).emergencyWithdraw(0))
      .to.be.revertedWith("Nothing to withdraw");
  });

  it("should return all staked tokens", async function () {
    await staking.connect(user1).deposit(0, ethers.parseEther("100"));
    const balanceBefore = await tokenA.balanceOf(user1.address);
    await staking.connect(user1).emergencyWithdraw(0);
    const balanceAfter = await tokenA.balanceOf(user1.address);
    expect(balanceAfter - balanceBefore).to.equal(ethers.parseEther("100"));
  });

  it("should reset user storage", async function () {
    await staking.connect(user1).deposit(0, ethers.parseEther("100"));
    await staking.connect(user1).emergencyWithdraw(0);
    const userInfo = await staking.userInfo(0, user1.address);
    expect(userInfo.amount).to.equal(0);
    expect(userInfo.rewardDebt).to.equal(0);
  });

  it("should decrement pool totalStaked", async function () {
    await staking.connect(user1).deposit(0, ethers.parseEther("100"));
    await staking.connect(user1).emergencyWithdraw(0);
    const pool = await staking.poolInfo(0);
    expect(pool.totalStaked).to.equal(0);
  });

  it("should not distribute rewards on emergency withdrawal", async function () {
    await staking.connect(user1).deposit(0, ethers.parseEther("100"));
    await rewardToken.transfer(staking.target, ethers.parseEther("1000"));
    await ethers.provider.send("evm_increaseTime", [86400]);
    await ethers.provider.send("evm_mine");

    const balanceBefore = await rewardToken.balanceOf(user1.address);
    await staking.connect(user1).emergencyWithdraw(0);
    const balanceAfter = await rewardToken.balanceOf(user1.address);
    // No reward tokens should have been received
    expect(balanceAfter - balanceBefore).to.equal(0);
  });

  it("should emit EmergencyWithdraw event", async function () {
    await staking.connect(user1).deposit(0, ethers.parseEther("100"));
    await expect(staking.connect(user1).emergencyWithdraw(0))
      .to.emit(staking, "EmergencyWithdraw")
      .withArgs(user1.address, 0, ethers.parseEther("100"));
  });

  it("should work during any contract state", async function () {
    // Deposit and advance time so rewards accrue
    await staking.connect(user1).deposit(0, ethers.parseEther("100"));
    await rewardToken.transfer(staking.target, ethers.parseEther("1000"));
    await ethers.provider.send("evm_increaseTime", [3600]);
    await ethers.provider.send("evm_mine");
    // Emergency withdraw succeeds even when rewards are pending
    await expect(staking.connect(user1).emergencyWithdraw(0))
      .to.emit(staking, "EmergencyWithdraw");
    // User got their tokens back
    const userInfo = await staking.userInfo(0, user1.address);
    expect(userInfo.amount).to.equal(0);
  });
});
