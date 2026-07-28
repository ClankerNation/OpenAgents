const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("StakingRewards", function () {
  let stakingRewards, stakingToken, rewardToken;
  let owner, staker1, staker2;

  beforeEach(async function () {
    [owner, staker1, staker2] = await ethers.getSigners();

    const TestToken = await ethers.getContractFactory("TestToken");
    stakingToken = await TestToken.deploy("Staking Token", "STK");
    await stakingToken.waitForDeployment();

    rewardToken = await TestToken.deploy("Reward Token", "RWD");
    await rewardToken.waitForDeployment();

    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    stakingRewards = await StakingRewards.deploy(stakingToken.target, rewardToken.target);
    await stakingRewards.waitForDeployment();

    // Mint tokens for testing (TestToken has open mint)
    await stakingToken.mint(staker1.address, ethers.parseEther("1000"));
    await stakingToken.mint(staker2.address, ethers.parseEther("1000"));
    await rewardToken.mint(stakingRewards.target, ethers.parseEther("10000"));

    // Initialize reward distribution
    await stakingRewards.notifyRewardAmount(ethers.parseEther("10000"));
  });

  it("should allow staking tokens", async function () {
    const amount = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(stakingRewards.target, amount);
    await stakingRewards.connect(staker1).stake(amount);

    const staked = await stakingRewards.balanceOf(staker1.address);
    expect(staked).to.equal(amount);
  });

  it("should accrue rewards over time", async function () {
    const amount = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(stakingRewards.target, amount);
    await stakingRewards.connect(staker1).stake(amount);

    await ethers.provider.send("evm_increaseTime", [86400]);
    await ethers.provider.send("evm_mine");

    const earned = await stakingRewards.earned(staker1.address);
    expect(earned).to.be.gt(0);
  });

  it("should allow withdrawal", async function () {
    const amount = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(stakingRewards.target, amount);
    await stakingRewards.connect(staker1).stake(amount);

    const withdrawAmount = ethers.parseEther("50");
    await stakingRewards.connect(staker1).withdraw(withdrawAmount);

    const remaining = await stakingRewards.balanceOf(staker1.address);
    expect(remaining).to.equal(ethers.parseEther("50"));
  });

  it("should track cumulative rewardPerTokenStored correctly", async function () {
    const amount1 = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(stakingRewards.target, amount1);
    await stakingRewards.connect(staker1).stake(amount1);
    
    const rewardPerToken1 = await stakingRewards.rewardPerToken();
    
    await ethers.provider.send("evm_increaseTime", [86400]);
    await ethers.provider.send("evm_mine");
    
    const rewardPerToken2 = await stakingRewards.rewardPerToken();
    expect(rewardPerToken2).to.be.gt(rewardPerToken1);
    
    const amount2 = ethers.parseEther("50");
    await stakingToken.connect(staker1).approve(stakingRewards.target, amount2);
    await stakingRewards.connect(staker1).stake(amount2);
    
    const rewardPerToken3 = await stakingRewards.rewardPerToken();
    expect(rewardPerToken3).to.be.gt(rewardPerToken2);
  });

  it("should update stored values on state-changing calls", async function () {
    const amount = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(stakingRewards.target, amount);
    
    let lastUpdateTime = await stakingRewards.lastUpdateTime();
    let rewardPerTokenStored = await stakingRewards.rewardPerTokenStored();
    
    await stakingRewards.connect(staker1).stake(amount);
    
    let newLastUpdateTime = await stakingRewards.lastUpdateTime();
    let newRewardPerTokenStored = await stakingRewards.rewardPerTokenStored();
    
    expect(newLastUpdateTime).to.not.equal(lastUpdateTime);
    expect(newRewardPerTokenStored).to.be.at.least(rewardPerTokenStored);
  });

  it("should not use per-user timestamp calculations", async function () {
    // First stake by staker1 to create non-zero total supply
    const amount1 = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(stakingRewards.target, amount1);
    await stakingRewards.connect(staker1).stake(amount1);

    // Advance time so rewardPerTokenStored becomes non-zero
    await ethers.provider.send("evm_increaseTime", [86400]);
    await ethers.provider.send("evm_mine");

    // staker2 stakes after rewards have accrued; updateReward uses global rewardPerTokenStored,
    // not per-user timestamps, so userRewardPerTokenPaid tracks cumulative value
    const amount2 = ethers.parseEther("100");
    await stakingToken.connect(staker2).approve(stakingRewards.target, amount2);
    await stakingRewards.connect(staker2).stake(amount2);
    
    const userRewardPerTokenPaid = await stakingRewards.userRewardPerTokenPaid(staker2.address);
    expect(userRewardPerTokenPaid).to.not.equal(0);
  });

  it("should calculate rewards via cumulative rewardPerToken", async function () {
    const amount1 = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(stakingRewards.target, amount1);
    await stakingRewards.connect(staker1).stake(amount1);
    
    const rewardPerToken1 = await stakingRewards.rewardPerToken();
    const earned1 = await stakingRewards.earned(staker1.address);
    
    await ethers.provider.send("evm_increaseTime", [86400]);
    await ethers.provider.send("evm_mine");
    
    const rewardPerToken2 = await stakingRewards.rewardPerToken();
    const earned2 = await stakingRewards.earned(staker1.address);
    
    expect(rewardPerToken2).to.be.gt(rewardPerToken1);
    expect(earned2).to.be.gt(earned1);
  });

  it("rate changes should not retroactively affect past rewards", async function () {
    const amount = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(stakingRewards.target, amount);
    await stakingRewards.connect(staker1).stake(amount);
    
    await ethers.provider.send("evm_increaseTime", [86400]);
    await ethers.provider.send("evm_mine");
    
    const earned1 = await stakingRewards.earned(staker1.address);
    
    const newReward = ethers.parseEther("5000");
    await rewardToken.mint(stakingRewards.target, newReward);
    await stakingRewards.notifyRewardAmount(newReward);
    
    await ethers.provider.send("evm_increaseTime", [86400]);
    await ethers.provider.send("evm_mine");
    
    const earned2 = await stakingRewards.earned(staker1.address);
    
    expect(earned2).to.be.gt(earned1);
    
    const increase = earned2 - earned1;
    expect(increase).to.be.gt(0);
  });

  it("multiple users staking at different times get correct proportional rewards", async function () {
    const amount1 = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(stakingRewards.target, amount1);
    await stakingRewards.connect(staker1).stake(amount1);
    
    await ethers.provider.send("evm_increaseTime", [43200]);
    await ethers.provider.send("evm_mine");
    
    const amount2 = ethers.parseEther("100");
    await stakingToken.connect(staker2).approve(stakingRewards.target, amount2);
    await stakingRewards.connect(staker2).stake(amount2);
    
    await ethers.provider.send("evm_increaseTime", [43200]);
    await ethers.provider.send("evm_mine");
    
    const earned1 = await stakingRewards.earned(staker1.address);
    const earned2 = await stakingRewards.earned(staker2.address);
    
    expect(earned1).to.be.gt(earned2);
    
    const ratio = (earned1 * 100n) / earned2;
    expect(ratio).to.be.closeTo(300n, 30n);
  });

  it("should stop accruing rewards after periodFinish", async function () {
    const amount = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(stakingRewards.target, amount);
    await stakingRewards.connect(staker1).stake(amount);
    
    // Advance beyond periodFinish (7 days)
    await ethers.provider.send("evm_increaseTime", [604800]);
    await ethers.provider.send("evm_mine");
    
    const earned1 = await stakingRewards.earned(staker1.address);
    
    // Advance more time after periodFinish
    await ethers.provider.send("evm_increaseTime", [86400]);
    await ethers.provider.send("evm_mine");
    
    const earned2 = await stakingRewards.earned(staker1.address);
    
    expect(earned2).to.equal(earned1);
  });

  it("should distribute rewards proportionally based on stake amount", async function () {
    const amount1 = ethers.parseEther("100");
    await stakingToken.connect(staker1).approve(stakingRewards.target, amount1);
    await stakingRewards.connect(staker1).stake(amount1);
    
    const amount2 = ethers.parseEther("200");
    await stakingToken.connect(staker2).approve(stakingRewards.target, amount2);
    await stakingRewards.connect(staker2).stake(amount2);
    
    await ethers.provider.send("evm_increaseTime", [86400]);
    await ethers.provider.send("evm_mine");
    
    const earned1 = await stakingRewards.earned(staker1.address);
    const earned2 = await stakingRewards.earned(staker2.address);
    
    const ratio = (earned2 * 100n) / earned1;
    expect(ratio).to.be.closeTo(200n, 20n);
  });
});
