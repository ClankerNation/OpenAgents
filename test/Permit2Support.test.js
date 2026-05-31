const { expect } = require("chai");
const { ethers, network } = require("hardhat");

const PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3";

describe("Permit2 support", function () {
  let owner;
  let user;

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners();

    const MockPermit2 = await ethers.getContractFactory("MockPermit2");
    const mockPermit2 = await MockPermit2.deploy();
    await mockPermit2.waitForDeployment();

    const runtimeCode = await ethers.provider.getCode(await mockPermit2.getAddress());
    await network.provider.send("hardhat_setCode", [PERMIT2, runtimeCode]);
  });

  it("supports permit2 stake and keeps fallback approve flow", async function () {
    const AgentToken = await ethers.getContractFactory("AgentToken");
    const stakingToken = await AgentToken.deploy("Stake", "STK", 0);
    const rewardToken = await AgentToken.deploy("Reward", "RWD", 0);
    await stakingToken.waitForDeployment();
    await rewardToken.waitForDeployment();

    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    const stakingRewards = await StakingRewards.deploy(
      await stakingToken.getAddress(),
      await rewardToken.getAddress()
    );
    await stakingRewards.waitForDeployment();

    const permitStakeAmount = ethers.parseEther("10");
    const fallbackStakeAmount = ethers.parseEther("5");

    await stakingToken.mint(user.address, permitStakeAmount + fallbackStakeAmount);
    await rewardToken.mint(await stakingRewards.getAddress(), ethers.parseEther("100"));

    await stakingToken.connect(user).approve(PERMIT2, permitStakeAmount);
    await stakingRewards.connect(user).stakeWithPermit2(
      user.address,
      permitStakeAmount,
      1,
      Math.floor(Date.now() / 1000) + 3600,
      "0x11"
    );

    expect(await stakingRewards.balanceOf(user.address)).to.equal(permitStakeAmount);

    await stakingToken.connect(user).approve(await stakingRewards.getAddress(), fallbackStakeAmount);
    await stakingRewards.connect(user).stake(fallbackStakeAmount);

    expect(await stakingRewards.balanceOf(user.address)).to.equal(
      permitStakeAmount + fallbackStakeAmount
    );
  });

  it("supports permit2 swap in AMMPool", async function () {
    const AgentToken = await ethers.getContractFactory("AgentToken");
    const tokenA = await AgentToken.deploy("TokenA", "TKA", 0);
    const tokenB = await AgentToken.deploy("TokenB", "TKB", 0);
    await tokenA.waitForDeployment();
    await tokenB.waitForDeployment();

    const AMMPool = await ethers.getContractFactory("AMMPool");
    const pool = await AMMPool.deploy(await tokenA.getAddress(), await tokenB.getAddress());
    await pool.waitForDeployment();

    const lpA = ethers.parseEther("100");
    const lpB = ethers.parseEther("100");
    await tokenA.mint(owner.address, lpA);
    await tokenB.mint(owner.address, lpB);
    await tokenA.approve(await pool.getAddress(), lpA);
    await tokenB.approve(await pool.getAddress(), lpB);
    await pool.addLiquidity(lpA, lpB);

    const amountIn = ethers.parseEther("10");
    const balanceBBefore = await tokenB.balanceOf(user.address);
    await tokenA.mint(user.address, amountIn);
    await tokenA.connect(user).approve(PERMIT2, amountIn);

    await pool.connect(user).swapWithPermit2(
      user.address,
      await tokenA.getAddress(),
      amountIn,
      0,
      2,
      Math.floor(Date.now() / 1000) + 3600,
      "0x22"
    );

    const balanceBAfter = await tokenB.balanceOf(user.address);
    expect(balanceBAfter).to.be.gt(balanceBBefore);
  });

  it("supports permit2 collateral deposit in LendingPool", async function () {
    const AgentToken = await ethers.getContractFactory("AgentToken");
    const collateralToken = await AgentToken.deploy("Collateral", "COL", 0);
    const borrowToken = await AgentToken.deploy("Borrow", "BRW", 0);
    await collateralToken.waitForDeployment();
    await borrowToken.waitForDeployment();

    const MockPriceFeed = await ethers.getContractFactory("MockPriceFeed");
    const oracle = await MockPriceFeed.deploy();
    await oracle.waitForDeployment();

    const LendingPool = await ethers.getContractFactory("LendingPool");
    const pool = await LendingPool.deploy(
      await oracle.getAddress(),
      await collateralToken.getAddress(),
      await borrowToken.getAddress()
    );
    await pool.waitForDeployment();

    const amount = ethers.parseEther("15");
    await collateralToken.mint(user.address, amount);
    await collateralToken.connect(user).approve(PERMIT2, amount);

    await pool.connect(user).depositWithPermit2(
      user.address,
      amount,
      3,
      Math.floor(Date.now() / 1000) + 3600,
      "0x33"
    );

    const position = await pool.getPosition(user.address);
    expect(position[0]).to.equal(amount);
  });
});
