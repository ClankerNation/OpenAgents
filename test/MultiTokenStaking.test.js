const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MultiTokenStaking", function () {
  let multiStaking, stakeToken, rewardToken;
  let owner, user1, user2;

  beforeEach(async function () {
    [owner, user1, user2] = await ethers.getSigners();

    // Deploy mock tokens
    const StakingToken = await ethers.getContractFactory("StakingToken");
    stakeToken = await StakingToken.deploy();
    await stakeToken.waitForDeployment();

    const RewardToken = await ethers.getContractFactory("RewardToken");
    rewardToken = await RewardToken.deploy();
    await rewardToken.waitForDeployment();

    // Deploy MultiTokenStaking
    const MultiTokenStaking = await ethers.getContractFactory("MultiTokenStaking");
    multiStaking = await MultiTokenStaking.deploy(
      rewardToken.target,
      ethers.parseEther("1") // 1 reward token per second
    );
    await multiStaking.waitForDeployment();

    // Mint tokens for users and contract
    await stakeToken.mint(user1.address, ethers.parseEther("1000"));
    await stakeToken.mint(user2.address, ethers.parseEther("1000"));
    await rewardToken.mint(multiStaking.target, ethers.parseEther("10000"));

    // Add pool
    await multiStaking.addPool(100, stakeToken.target);
  });

  it("should allow normal deposit and check accounting", async function () {
    const amount = ethers.parseEther("100");
    await stakeToken.connect(user1).approve(multiStaking.target, amount);
    await multiStaking.connect(user1).deposit(0, amount);

    const pool = await multiStaking.poolInfo(0);
    expect(pool.totalStaked).to.equal(amount);

    const userInfo = await multiStaking.userInfo(0, user1.address);
    expect(userInfo.amount).to.equal(amount);
  });

  it("should allow emergencyWithdraw, return tokens without rewards, and update accounting", async function () {
    const amount = ethers.parseEther("100");
    await stakeToken.connect(user1).approve(multiStaking.target, amount);
    await multiStaking.connect(user1).deposit(0, amount);

    // Evm time passing to accumulate rewards
    await ethers.provider.send("evm_increaseTime", [3600]);
    await ethers.provider.send("evm_mine");

    // Pre-balances
    const initialStakeBalance = await stakeToken.balanceOf(user1.address);
    const initialRewardBalance = await rewardToken.balanceOf(user1.address);

    // Call emergencyWithdraw
    const tx = await multiStaking.connect(user1).emergencyWithdraw(0);

    // Check event emission
    await expect(tx)
      .to.emit(multiStaking, "EmergencyWithdraw")
      .withArgs(user1.address, 0, amount);

    // Check balances
    const finalStakeBalance = await stakeToken.balanceOf(user1.address);
    const finalRewardBalance = await rewardToken.balanceOf(user1.address);

    // Staked tokens returned
    expect(finalStakeBalance - initialStakeBalance).to.equal(amount);
    // No rewards distributed
    expect(finalRewardBalance).to.equal(initialRewardBalance);

    // Check contract/user state
    const pool = await multiStaking.poolInfo(0);
    expect(pool.totalStaked).to.equal(0);

    const userInfo = await multiStaking.userInfo(0, user1.address);
    expect(userInfo.amount).to.equal(0);
    expect(userInfo.rewardDebt).to.equal(0);
  });

  it("should revert if user has nothing to withdraw", async function () {
    await expect(
      multiStaking.connect(user1).emergencyWithdraw(0)
    ).to.be.revertedWith("emergencyWithdraw: nothing to withdraw");
  });
});
