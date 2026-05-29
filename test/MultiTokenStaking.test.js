const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MultiTokenStaking", function () {
  let staking, rewardToken, stakeToken;
  let owner, user;

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners();

    const RewardToken = await ethers.getContractFactory("RewardToken");
    rewardToken = await RewardToken.deploy();
    await rewardToken.waitForDeployment();

    const StakingToken = await ethers.getContractFactory("StakingToken");
    stakeToken = await StakingToken.deploy();
    await stakeToken.waitForDeployment();

    const MultiTokenStaking = await ethers.getContractFactory("MultiTokenStaking");
    staking = await MultiTokenStaking.deploy(rewardToken.target, ethers.parseEther("1"));
    await staking.waitForDeployment();

    // Mint reward tokens to MultiTokenStaking so it can pay out harvest rewards
    await rewardToken.mint(staking.target, ethers.parseEther("1000"));

    // Add staking pool
    await staking.connect(owner).addPool(100, stakeToken.target);

    // Mint stake tokens to user
    await stakeToken.mint(user.address, ethers.parseEther("1000"));
    await stakeToken.connect(user).approve(staking.target, ethers.parseEther("1000"));
  });

  it("should allow stake and emergency withdraw", async function () {
    const stakeAmount = ethers.parseEther("100");

    // Deposit to pool 0
    await staking.connect(user).deposit(0, stakeAmount);

    // Check pool totalStaked
    let pool = await staking.poolInfo(0);
    expect(pool.totalStaked).to.equal(stakeAmount);

    // Check user info
    let userInfo = await staking.userInfo(0, user.address);
    expect(userInfo.amount).to.equal(stakeAmount);

    // Perform emergency withdraw
    const tx = await staking.connect(user).emergencyWithdraw(0);

    // Verify event emission
    await expect(tx)
      .to.emit(staking, "EmergencyWithdraw")
      .withArgs(user.address, 0, stakeAmount);

    // Check final states
    pool = await staking.poolInfo(0);
    expect(pool.totalStaked).to.equal(0);

    userInfo = await staking.userInfo(0, user.address);
    expect(userInfo.amount).to.equal(0);
    expect(userInfo.rewardDebt).to.equal(0);

    // Verify token balance returned to user
    const userBal = await stakeToken.balanceOf(user.address);
    expect(userBal).to.equal(ethers.parseEther("1000"));
  });
});
