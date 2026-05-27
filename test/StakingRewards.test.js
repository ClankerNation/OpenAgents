const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("StakingRewards", function () {
  const REWARD_DURATION = 7 * 24 * 60 * 60;

  let stakingRewards;
  let stakingToken;
  let rewardToken;
  let owner;
  let staker1;
  let staker2;

  async function deployToken(name, symbol) {
    const AgentToken = await ethers.getContractFactory("AgentToken");
    return AgentToken.deploy(name, symbol, 0);
  }

  async function deployFixture() {
    [owner, staker1, staker2] = await ethers.getSigners();

    stakingToken = await deployToken("Stake Token", "STK");
    rewardToken = await deployToken("Reward Token", "RWD");

    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    stakingRewards = await StakingRewards.deploy(
      await stakingToken.getAddress(),
      await rewardToken.getAddress()
    );

    const stakeAmount = ethers.parseEther("1000");
    await stakingToken.mint(staker1.address, stakeAmount);
    await stakingToken.mint(staker2.address, stakeAmount);
    await rewardToken.mint(
      await stakingRewards.getAddress(),
      ethers.parseEther("1000000")
    );
  }

  async function stakeAs(staker, amount) {
    await stakingToken
      .connect(staker)
      .approve(await stakingRewards.getAddress(), amount);
    await stakingRewards.connect(staker).stake(amount);
  }

  beforeEach(async function () {
    await deployFixture();
  });

  it("stops accruing rewards after the reward period ends", async function () {
    const stakeAmount = ethers.parseEther("100");
    const rewardAmount = ethers.parseEther("604800");

    await stakeAs(staker1, stakeAmount);
    await stakingRewards.notifyRewardAmount(rewardAmount);

    await time.increase(REWARD_DURATION);
    const earnedAtFinish = await stakingRewards.earned(staker1.address);

    await time.increase(30 * 24 * 60 * 60);
    const earnedAfterFinish = await stakingRewards.earned(staker1.address);

    expect(earnedAfterFinish).to.equal(earnedAtFinish);
    expect(earnedAtFinish).to.equal(rewardAmount);
  });

  it("does not retroactively apply a new reward rate to already accrued rewards", async function () {
    const stakeAmount = ethers.parseEther("100");
    const firstReward = ethers.parseEther("604800");
    const secondReward = ethers.parseEther("1209600");

    await stakeAs(staker1, stakeAmount);
    await stakingRewards.notifyRewardAmount(firstReward);

    await time.increase(REWARD_DURATION / 2);
    const earnedBeforeRateChange = await stakingRewards.earned(staker1.address);

    await stakingRewards.notifyRewardAmount(secondReward);
    const earnedImmediatelyAfterRateChange = await stakingRewards.earned(
      staker1.address
    );

    expect(earnedImmediatelyAfterRateChange).to.be.closeTo(
      earnedBeforeRateChange,
      ethers.parseEther("2")
    );
    expect(earnedBeforeRateChange).to.be.closeTo(
      firstReward / 2n,
      ethers.parseEther("2")
    );

    await time.increase(REWARD_DURATION);
    const earnedAfterNewPeriod = await stakingRewards.earned(staker1.address);

    expect(earnedAfterNewPeriod).to.be.closeTo(
      firstReward + secondReward,
      ethers.parseEther("4")
    );
  });

  it("keeps proportional rewards correct when users stake at different times", async function () {
    const stakeAmount = ethers.parseEther("100");
    const rewardAmount = ethers.parseEther("604800");

    await stakeAs(staker1, stakeAmount);
    await stakingRewards.notifyRewardAmount(rewardAmount);

    await time.increase(REWARD_DURATION / 2);
    await stakeAs(staker2, stakeAmount);

    await time.increase(REWARD_DURATION / 2);

    const earned1 = await stakingRewards.earned(staker1.address);
    const earned2 = await stakingRewards.earned(staker2.address);

    expect(earned1).to.be.closeTo(
      ethers.parseEther("453600"),
      ethers.parseEther("3")
    );
    expect(earned2).to.be.closeTo(
      ethers.parseEther("151200"),
      ethers.parseEther("3")
    );
    expect(earned1 + earned2).to.be.closeTo(rewardAmount, ethers.parseEther("6"));
  });

  it("pays the proportional split once and does not overpay after finish", async function () {
    const stakeAmount = ethers.parseEther("100");
    const rewardAmount = ethers.parseEther("604800");

    await stakeAs(staker1, stakeAmount);
    await stakingRewards.notifyRewardAmount(rewardAmount);

    await time.increase(REWARD_DURATION / 2);
    await stakeAs(staker2, stakeAmount);

    await time.increase(REWARD_DURATION / 2);

    await stakingRewards.connect(staker1).getReward();
    await stakingRewards.connect(staker2).getReward();

    const paid1 = await rewardToken.balanceOf(staker1.address);
    const paid2 = await rewardToken.balanceOf(staker2.address);
    const contractBalanceAfterClaims = await rewardToken.balanceOf(
      await stakingRewards.getAddress()
    );

    expect(paid1).to.be.closeTo(
      ethers.parseEther("453600"),
      ethers.parseEther("3")
    );
    expect(paid2).to.be.closeTo(
      ethers.parseEther("151200"),
      ethers.parseEther("3")
    );
    expect(paid1 + paid2).to.be.closeTo(rewardAmount, ethers.parseEther("6"));

    await time.increase(30 * 24 * 60 * 60);
    await stakingRewards.connect(staker1).getReward();
    await stakingRewards.connect(staker2).getReward();

    expect(await rewardToken.balanceOf(staker1.address)).to.equal(paid1);
    expect(await rewardToken.balanceOf(staker2.address)).to.equal(paid2);
    expect(await rewardToken.balanceOf(await stakingRewards.getAddress())).to.equal(
      contractBalanceAfterClaims
    );
  });
});
