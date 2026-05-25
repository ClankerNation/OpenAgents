const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("MultiTokenStaking emergencyWithdraw", function () {
  let owner;
  let alice;
  let rewardToken;
  let stakeToken;
  let staking;

  const stakeAmount = ethers.parseEther("100");
  const initialSupply = ethers.parseEther("1000000");
  const rewardPerSecond = ethers.parseEther("1");

  beforeEach(async function () {
    [owner, alice] = await ethers.getSigners();

    const AgentToken = await ethers.getContractFactory("AgentToken");
    rewardToken = await AgentToken.deploy("Reward", "RWD", initialSupply);
    stakeToken = await AgentToken.deploy("Stake", "STK", initialSupply);

    const MultiTokenStaking = await ethers.getContractFactory("MultiTokenStaking");
    staking = await MultiTokenStaking.deploy(await rewardToken.getAddress(), rewardPerSecond);

    await staking.addPool(100, await stakeToken.getAddress());
    await rewardToken.transfer(await staking.getAddress(), ethers.parseEther("1000"));
    await stakeToken.transfer(alice.address, stakeAmount);
    await stakeToken.connect(alice).approve(await staking.getAddress(), stakeAmount);
  });

  it("returns staked tokens without distributing rewards and resets accounting", async function () {
    await staking.connect(alice).deposit(0, stakeAmount);
    await time.increase(3600);

    expect(await staking.pendingReward(0, alice.address)).to.be.gt(0);

    const rewardBefore = await rewardToken.balanceOf(alice.address);

    await expect(staking.connect(alice).emergencyWithdraw(0))
      .to.emit(staking, "EmergencyWithdraw")
      .withArgs(alice.address, 0, stakeAmount);

    const user = await staking.userInfo(0, alice.address);
    const pool = await staking.poolInfo(0);

    expect(user.amount).to.equal(0);
    expect(user.rewardDebt).to.equal(0);
    expect(pool.totalStaked).to.equal(0);
    expect(await stakeToken.balanceOf(alice.address)).to.equal(stakeAmount);
    expect(await rewardToken.balanceOf(alice.address)).to.equal(rewardBefore);
    expect(await staking.pendingReward(0, alice.address)).to.equal(0);
  });
});
