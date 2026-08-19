/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("StakingRewards Reentrancy Protection", function () {
  let stakingRewards, rewardsToken, maliciousToken;
  let owner, user1;

  before(async function () {
    [owner, user1] = await ethers.getSigners();

    const MaliciousToken = await ethers.getContractFactory("MaliciousToken");
    maliciousToken = await MaliciousToken.deploy();
    await maliciousToken.waitForDeployment();

    const Token = await ethers.getContractFactory("AgentToken");
    rewardsToken = await Token.deploy("Reward Token", "RWD", ethers.parseEther("1000000"));
    await rewardsToken.waitForDeployment();

    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    stakingRewards = await StakingRewards.deploy(maliciousToken.target, rewardsToken.target);
    await stakingRewards.waitForDeployment();

    await maliciousToken.setStaking(stakingRewards.target);

    // Fund user1
    await maliciousToken.transfer(user1.address, ethers.parseEther("1000"));
    
    // Fund staking contract with rewards
    await rewardsToken.transfer(stakingRewards.target, ethers.parseEther("10000"));
    await stakingRewards.notifyRewardAmount(ethers.parseEther("10000"));

    // User1 stakes
    await maliciousToken.connect(user1).approve(stakingRewards.target, ethers.MaxUint256);
    await stakingRewards.connect(user1).stake(ethers.parseEther("1000"));
  });

  it("should prevent reentrancy attack on withdraw via malicious token", async function () {
    // Advance time to accrue some rewards
    await ethers.provider.send("evm_increaseTime", [86400]);
    await ethers.provider.send("evm_mine");

    // Start attack
    await maliciousToken.connect(user1).startAttack(ethers.parseEther("500"));
    
    // Attempt withdraw - the malicious token will try to call withdraw again
    // This should revert due to nonReentrant (OZ v5 uses custom error)
    await expect(
      stakingRewards.connect(user1).withdraw(ethers.parseEther("500"))
    ).to.be.revertedWithCustomError(stakingRewards, "ReentrancyGuardReentrantCall");
  });

  it("should allow legitimate withdrawals", async function () {
    // Ensure attack mode is off
    await maliciousToken.connect(user1).stopAttack();
    
    const balBefore = await maliciousToken.balanceOf(user1.address);
    await stakingRewards.connect(user1).withdraw(ethers.parseEther("500"));
    const balAfter = await maliciousToken.balanceOf(user1.address);
    expect(balAfter - balBefore).to.equal(ethers.parseEther("500"));
  });
});
