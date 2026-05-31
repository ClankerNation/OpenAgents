const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MultiTokenStaking emergencyWithdraw", function () {
  let owner, staker;
  let stakeToken, rewardToken, staking;

  beforeEach(async function () {
    [owner, staker] = await ethers.getSigners();

    const AgentToken = await ethers.getContractFactory("AgentToken");
    stakeToken = await AgentToken.deploy("Stake Token", "STK", ethers.parseEther("1000000"));
    rewardToken = await AgentToken.deploy("Reward Token", "RWD", ethers.parseEther("1000000"));

    const MultiTokenStaking = await ethers.getContractFactory("MultiTokenStaking");
    staking = await MultiTokenStaking.deploy(await rewardToken.getAddress(), ethers.parseEther("1"));

    await staking.addPool(100, await stakeToken.getAddress());
    await rewardToken.transfer(await staking.getAddress(), ethers.parseEther("100000"));
    await stakeToken.transfer(staker.address, ethers.parseEther("1000"));
  });

  it("returns staked tokens without distributing rewards and resets accounting", async function () {
    const amount = ethers.parseEther("100");
    await stakeToken.connect(staker).approve(await staking.getAddress(), amount);
    await staking.connect(staker).deposit(0, amount);

    await ethers.provider.send("evm_increaseTime", [3600]);
    await ethers.provider.send("evm_mine", []);

    const pending = await staking.pendingReward(0, staker.address);
    expect(pending).to.be.gt(0n);

    const rewardBalanceBefore = await rewardToken.balanceOf(staker.address);
    const stakeBalanceBefore = await stakeToken.balanceOf(staker.address);

    await expect(staking.connect(staker).emergencyWithdraw(0))
      .to.emit(staking, "EmergencyWithdraw")
      .withArgs(staker.address, 0, amount);

    const user = await staking.userInfo(0, staker.address);
    const pool = await staking.poolInfo(0);

    expect(user.amount).to.equal(0n);
    expect(user.rewardDebt).to.equal(0n);
    expect(pool.totalStaked).to.equal(0n);
    expect(await rewardToken.balanceOf(staker.address)).to.equal(rewardBalanceBefore);
    expect(await stakeToken.balanceOf(staker.address)).to.equal(stakeBalanceBefore + amount);
    expect(await staking.pendingReward(0, staker.address)).to.equal(0n);
  });
});
