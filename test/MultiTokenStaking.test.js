const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MultiTokenStaking", function () {
  let staking, stakeToken, rewardToken;
  let owner, staker;

  beforeEach(async function () {
    [owner, staker] = await ethers.getSigners();

    const MockERC20 = await ethers.getContractFactory("MockERC20");
    stakeToken = await MockERC20.deploy("Stake Token", "STK");
    await stakeToken.waitForDeployment();

    rewardToken = await MockERC20.deploy("Reward Token", "RWD");
    await rewardToken.waitForDeployment();

    const MultiTokenStaking = await ethers.getContractFactory("MultiTokenStaking");
    staking = await MultiTokenStaking.deploy(
      await rewardToken.getAddress(),
      ethers.parseEther("0.01")
    );
    await staking.waitForDeployment();

    // Mint tokens to staker
    await stakeToken.mint(staker.address, ethers.parseEther("1000"));
    // Mint reward tokens to staking contract
    await rewardToken.mint(await staking.getAddress(), ethers.parseEther("10000"));

    // Add a pool
    await staking.connect(owner).addPool(100, await stakeToken.getAddress());
  });

  describe("emergencyWithdraw", function () {
    it("should return staked tokens and reset user state", async function () {
      const depositAmount = ethers.parseEther("100");

      await stakeToken.connect(staker).approve(await staking.getAddress(), depositAmount);
      await staking.connect(staker).deposit(0, depositAmount);

      // Verify deposit
      let user = await staking.userInfo(0, staker.address);
      expect(user.amount).to.equal(depositAmount);
      expect(user.rewardDebt).to.be.gt(0);

      let pool = await staking.poolInfo(0);
      expect(pool.totalStaked).to.equal(depositAmount);

      const balanceBefore = await stakeToken.balanceOf(staker.address);

      // Perform emergency withdraw
      const tx = await staking.connect(staker).emergencyWithdraw(0);
      const receipt = await tx.wait();

      // Verify tokens returned
      const balanceAfter = await stakeToken.balanceOf(staker.address);
      expect(balanceAfter - balanceBefore).to.equal(depositAmount);

      // Verify user state reset
      user = await staking.userInfo(0, staker.address);
      expect(user.amount).to.equal(0);
      expect(user.rewardDebt).to.equal(0);

      // Verify pool totalStaked decreased
      pool = await staking.poolInfo(0);
      expect(pool.totalStaked).to.equal(0);

      // Verify event emitted
      const event = receipt.logs.find(
        (log) => log.fragment && log.fragment.name === "EmergencyWithdraw"
      );
      expect(event).to.not.be.undefined;
      expect(event.args.user).to.equal(staker.address);
      expect(event.args.pid).to.equal(0);
      expect(event.args.amount).to.equal(depositAmount);
    });

    it("should revert if user has no stake", async function () {
      await expect(
        staking.connect(staker).emergencyWithdraw(0)
      ).to.be.revertedWith("MultiStaking: nothing to withdraw");
    });

    it("should not pay pending rewards on emergency withdraw", async function () {
      const depositAmount = ethers.parseEther("100");

      await stakeToken.connect(staker).approve(await staking.getAddress(), depositAmount);
      await staking.connect(staker).deposit(0, depositAmount);

      // Advance time to accrue rewards
      await ethers.provider.send("evm_increaseTime", [86400]); // 1 day
      await ethers.provider.send("evm_mine");

      const rewardBalanceBefore = await rewardToken.balanceOf(staker.address);

      await staking.connect(staker).emergencyWithdraw(0);

      const rewardBalanceAfter = await rewardToken.balanceOf(staker.address);
      // No rewards should have been paid
      expect(rewardBalanceAfter - rewardBalanceBefore).to.equal(0);
    });
  });
});
