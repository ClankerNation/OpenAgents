// @contributor Codex
// @platform Private platform/session initialization text omitted; public OpenAgents #94 bounty test artifact.
// @runtime os=Darwin arch=arm64 working_dir=/Users/nicdunz/Documents/money making/runs/2026-05-20-openagents-agenttoken-permit-158/OpenAgents
// @date 2026-05-20T10:04:54Z

const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("MultiTokenStaking pool guards", function () {
  async function deployToken(name, symbol, initialSupply = 0n) {
    const Token = await ethers.getContractFactory("AgentToken");
    const token = await Token.deploy(name, symbol, initialSupply);
    await token.waitForDeployment();
    return token;
  }

  async function deployStaking(rewardPerSecond = 1n) {
    const rewardToken = await deployToken("Reward", "RWD");
    const Staking = await ethers.getContractFactory("MultiTokenStaking");
    const staking = await Staking.deploy(await rewardToken.getAddress(), rewardPerSecond);
    await staking.waitForDeployment();
    return { staking, rewardToken };
  }

  it("rejects zero reward and stake token addresses", async function () {
    const Staking = await ethers.getContractFactory("MultiTokenStaking");
    await expect(Staking.deploy(ethers.ZeroAddress, 1n)).to.be.revertedWith("MultiStaking: zero reward token");

    const { staking } = await deployStaking();
    await expect(staking.addPool(100n, ethers.ZeroAddress)).to.be.revertedWith("MultiStaking: zero stake token");
  });

  it("rejects duplicate stake-token pools", async function () {
    const { staking } = await deployStaking();
    const stakeToken = await deployToken("Stake", "STK");
    const stakeTokenAddress = await stakeToken.getAddress();

    await staking.addPool(100n, stakeTokenAddress);

    expect(await staking.poolExists(stakeTokenAddress)).to.equal(true);
    await expect(staking.addPool(1n, stakeTokenAddress)).to.be.revertedWith("MultiStaking: duplicate pool");
  });

  it("lets the owner update a pool weight and total allocation", async function () {
    const { staking } = await deployStaking();
    const stakeToken = await deployToken("Stake", "STK");

    await staking.addPool(100n, await stakeToken.getAddress());
    await expect(staking.setPoolWeight(0, 250n))
      .to.emit(staking, "PoolWeightUpdated")
      .withArgs(0, 100n, 250n);

    const pool = await staking.poolInfo(0);
    expect(pool.allocPoint).to.equal(250n);
    expect(await staking.totalAllocPoint()).to.equal(250n);
  });

  it("uses full-precision reward math so large emissions do not overflow", async function () {
    const [, alice] = await ethers.getSigners();
    const rewardPerSecond = 1n << 254n;
    const { staking } = await deployStaking(rewardPerSecond);
    const stakeToken = await deployToken("StakeA", "STKA");
    const secondStakeToken = await deployToken("StakeB", "STKB");
    const amount = ethers.parseEther("1");

    await staking.addPool(1n, await stakeToken.getAddress());
    await staking.addPool(2n, await secondStakeToken.getAddress());
    await stakeToken.mint(alice.address, amount);
    await stakeToken.connect(alice).approve(await staking.getAddress(), amount);
    await staking.connect(alice).deposit(0, amount);

    await time.increase(4);

    const pending = await staking.pendingReward(0, alice.address);
    expect(pending).to.be.gt(0n);
    await expect(staking.updatePool(0)).not.to.be.reverted;
  });

  it("keeps allocation precision while avoiding overflow-prone multiplication order", async function () {
    const [, alice] = await ethers.getSigners();
    const { staking } = await deployStaking(199n);
    const stakeToken = await deployToken("StakeC", "STKC");
    const secondStakeToken = await deployToken("StakeD", "STKD");

    await staking.addPool(50n, await stakeToken.getAddress());
    await staking.addPool(50n, await secondStakeToken.getAddress());
    await stakeToken.mint(alice.address, 1n);
    await stakeToken.connect(alice).approve(await staking.getAddress(), 1n);
    await staking.connect(alice).deposit(0, 1n);

    await time.increase(1);

    expect(await staking.pendingReward(0, alice.address)).to.equal(99n);
  });
});
