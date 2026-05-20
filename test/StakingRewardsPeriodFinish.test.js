const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("StakingRewards period finish", function () {
  const rewardsDuration = 7n * 24n * 60n * 60n;

  async function deployToken(name, symbol, initialSupply = 0n) {
    const Token = await ethers.getContractFactory("AgentToken");
    const token = await Token.deploy(name, symbol, initialSupply);
    await token.waitForDeployment();
    return token;
  }

  async function deployRewards() {
    const stakingToken = await deployToken("Stake", "STK");
    const rewardsToken = await deployToken("Reward", "RWD");
    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    const rewards = await StakingRewards.deploy(
      await stakingToken.getAddress(),
      await rewardsToken.getAddress()
    );
    await rewards.waitForDeployment();
    return { stakingToken, rewardsToken, rewards };
  }

  it("stops accruing rewards after periodFinish", async function () {
    const [, alice] = await ethers.getSigners();
    const { stakingToken, rewardsToken, rewards } = await deployRewards();
    const stakeAmount = ethers.parseEther("100");
    const rewardAmount = ethers.parseEther("700");

    await stakingToken.mint(alice.address, stakeAmount);
    await stakingToken.connect(alice).approve(await rewards.getAddress(), stakeAmount);
    await rewards.connect(alice).stake(stakeAmount);
    await rewardsToken.mint(await rewards.getAddress(), rewardAmount);
    await rewards.notifyRewardAmount(rewardAmount);

    await time.increase(Number(rewardsDuration) + 1);
    const earnedAtFinish = await rewards.earned(alice.address);

    await time.increase(3600);
    expect(await rewards.earned(alice.address)).to.equal(earnedAtFinish);
  });

  it("restricts reward notification to the configured distributor", async function () {
    const [, distributor, stranger] = await ethers.getSigners();
    const { rewardsToken, rewards } = await deployRewards();
    const rewardAmount = ethers.parseEther("1");

    await expect(rewards.connect(stranger).notifyRewardAmount(rewardAmount))
      .to.be.revertedWith("StakingRewards: not distributor");

    await rewards.setRewardsDistributor(distributor.address);
    await rewardsToken.mint(await rewards.getAddress(), rewardAmount);

    await expect(rewards.connect(distributor).notifyRewardAmount(rewardAmount))
      .to.emit(rewards, "RewardAdded")
      .withArgs(rewardAmount);
  });

  it("keeps small reward schedules below the precision-loss threshold", async function () {
    const [, alice] = await ethers.getSigners();
    const { stakingToken, rewardsToken, rewards } = await deployRewards();
    const rewardAmount = 500000n;
    const maxAllowedLoss = rewardAmount / 10000n;

    await stakingToken.mint(alice.address, 1n);
    await stakingToken.connect(alice).approve(await rewards.getAddress(), 1n);
    await rewards.connect(alice).stake(1n);
    await rewardsToken.mint(await rewards.getAddress(), rewardAmount);
    await rewards.notifyRewardAmount(rewardAmount);

    await time.increase(Number(rewardsDuration) + 1);

    expect(await rewards.earned(alice.address)).to.be.gte(rewardAmount - maxAllowedLoss);
  });
});
