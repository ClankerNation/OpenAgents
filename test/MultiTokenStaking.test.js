const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MultiTokenStaking - Emergency Withdraw", function () {
  let multiTokenStaking;
  let stakeToken, rewardToken;
  let owner, staker;

  before(async function () {
    [owner, staker] = await ethers.getSigners();

    // Deploy mock ERC20 tokens for staking and rewards
    const MockERC20 = await ethers.getContractFactory("MockERC20");
    stakeToken = await MockERC20.deploy("Stake Token", "STK");
    await stakeToken.waitForDeployment();

    rewardToken = await MockERC20.deploy("Reward Token", "RWD");
    await rewardToken.waitForDeployment();

    // Deploy MultiTokenStaking with reward token and 1 token/sec reward rate
    const MultiTokenStaking = await ethers.getContractFactory("MultiTokenStaking");
    multiTokenStaking = await MultiTokenStaking.deploy(
      await rewardToken.getAddress(),
      ethers.parseEther("1") // 1 reward token per second
    );
    await multiTokenStaking.waitForDeployment();

    // Mint stake tokens to staker
    await stakeToken.mint(staker.address, ethers.parseEther("1000"));

    // Mint reward tokens to contract
    await rewardToken.mint(
      await multiTokenStaking.getAddress(),
      ethers.parseEther("10000")
    );

    // Add a pool for the stake token with 100 alloc points
    await multiTokenStaking.addPool(100, await stakeToken.getAddress());
  });

  describe("emergencyWithdraw", function () {
    it("should return all staked tokens and reset user state", async function () {
      const stakeAmount = ethers.parseEther("100");

      // Approve and stake
      await stakeToken.connect(staker).approve(
        await multiTokenStaking.getAddress(),
        stakeAmount
      );
      await multiTokenStaking.connect(staker).deposit(0, stakeAmount);

      // Verify staked
      const userInfo = await multiTokenStaking.userInfo(0, staker.address);
      expect(userInfo.amount).to.equal(stakeAmount);

      const poolBefore = await multiTokenStaking.poolInfo(0);
      expect(poolBefore.totalStaked).to.equal(stakeAmount);

      // Record balance before emergency withdraw
      const balanceBefore = await stakeToken.balanceOf(staker.address);

      // Perform emergency withdraw
      await expect(
        multiTokenStaking.connect(staker).emergencyWithdraw(0)
      )
        .to.emit(multiTokenStaking, "EmergencyWithdraw")
        .withArgs(staker.address, 0, stakeAmount);

      // Verify tokens returned
      const balanceAfter = await stakeToken.balanceOf(staker.address);
      expect(balanceAfter - balanceBefore).to.equal(stakeAmount);

      // Verify user state reset
      const userInfoAfter = await multiTokenStaking.userInfo(0, staker.address);
      expect(userInfoAfter.amount).to.equal(0);
      expect(userInfoAfter.rewardDebt).to.equal(0);

      // Verify pool total decreased
      const poolAfter = await multiTokenStaking.poolInfo(0);
      expect(poolAfter.totalStaked).to.equal(0);
    });

    it("should not distribute rewards on emergency withdrawal", async function () {
      // Stake fresh tokens
      const stakeAmount = ethers.parseEther("50");
      await stakeToken.connect(staker).approve(
        await multiTokenStaking.getAddress(),
        stakeAmount
      );
      await multiTokenStaking.connect(staker).deposit(0, stakeAmount);

      // Advance time to accrue some rewards
      await ethers.provider.send("evm_increaseTime", [3600]); // 1 hour
      await ethers.provider.send("evm_mine");

      // Check pending rewards exist
      const pendingBefore = await multiTokenStaking.pendingReward(
        0,
        staker.address
      );
      expect(pendingBefore).to.be.gt(0);

      // Record reward balance before emergency withdraw
      const rewardBalanceBefore = await rewardToken.balanceOf(staker.address);

      // Emergency withdraw
      await multiTokenStaking.connect(staker).emergencyWithdraw(0);

      // Verify no reward tokens received
      const rewardBalanceAfter = await rewardToken.balanceOf(staker.address);
      expect(rewardBalanceAfter).to.equal(rewardBalanceBefore);
    });

    it("should revert if user has no staked tokens", async function () {
      await expect(
        multiTokenStaking.connect(staker).emergencyWithdraw(0)
      ).to.be.revertedWith("MultiStaking: no staked tokens");
    });

    it("should allow re-staking after emergency withdraw", async function () {
      // Stake
      const stakeAmount = ethers.parseEther("30");
      await stakeToken.connect(staker).approve(
        await multiTokenStaking.getAddress(),
        stakeAmount
      );
      await multiTokenStaking.connect(staker).deposit(0, stakeAmount);

      // Emergency withdraw
      await multiTokenStaking.connect(staker).emergencyWithdraw(0);

      // Re-stake
      await stakeToken.connect(staker).approve(
        await multiTokenStaking.getAddress(),
        stakeAmount
      );
      await multiTokenStaking.connect(staker).deposit(0, stakeAmount);

      // Verify re-staked
      const userInfo = await multiTokenStaking.userInfo(0, staker.address);
      expect(userInfo.amount).to.equal(stakeAmount);
    });
  });
});
