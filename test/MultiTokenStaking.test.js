/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MultiTokenStaking Emergency Withdraw", function () {
  let staking, stakeToken, rewardToken;
  let owner, user1;
  const rewardPerSecond = ethers.parseEther("1");

  before(async function () {
    [owner, user1] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("AgentToken");
    stakeToken = await Token.deploy("Stake Token", "STK", ethers.parseEther("1000000"));
    await stakeToken.waitForDeployment();

    rewardToken = await Token.deploy("Reward Token", "RWD", ethers.parseEther("1000000"));
    await rewardToken.waitForDeployment();

    const Staking = await ethers.getContractFactory("MultiTokenStaking");
    staking = await Staking.deploy(rewardToken.target, rewardPerSecond);
    await staking.waitForDeployment();

    await staking.addPool(100, stakeToken.target);

    await stakeToken.transfer(user1.address, ethers.parseEther("1000"));
    await stakeToken.connect(user1).approve(staking.target, ethers.MaxUint256);
  });

  it("should allow emergency withdrawal and reset state", async function () {
    const depositAmount = ethers.parseEther("100");
    await staking.connect(user1).deposit(0, depositAmount);

    const userBefore = await staking.userInfo(0, user1.address);
    expect(userBefore.amount).to.equal(depositAmount);

    const tx = await staking.connect(user1).emergencyWithdraw(0);
    const receipt = await tx.wait();

    // Check event
    const event = receipt.logs.find(log => {
      try {
        const parsed = staking.interface.parseLog(log);
        return parsed && parsed.name === "EmergencyWithdraw";
      } catch (e) { return false; }
    });
    expect(event).to.not.be.undefined;

    const userAfter = await staking.userInfo(0, user1.address);
    expect(userAfter.amount).to.equal(0n);
    expect(userAfter.rewardDebt).to.equal(0n);

    const pool = await staking.poolInfo(0);
    expect(pool.totalStaked).to.equal(0n);

    const userBalance = await stakeToken.balanceOf(user1.address);
    expect(userBalance).to.equal(ethers.parseEther("1000"));
  });
});
