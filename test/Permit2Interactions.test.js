const { expect } = require("chai");
const { ethers, network } = require("hardhat");

// Contributor: Codex for charlie12520.
// Runtime instructions: private platform instructions are intentionally not disclosed.
// Environment: Windows x64, PowerShell, C:\Users\charl\Desktop\AI STUFF\ten_buck_attempt\repos\OpenAgents.

const PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3";
const SIGNATURE = "0x1234";

async function deployContract(name, args = []) {
  const factory = await ethers.getContractFactory(name);
  const contract = await factory.deploy(...args);
  await contract.waitForDeployment();
  return contract;
}

async function installPermit2Mock() {
  const mock = await deployContract("MockPermit2");
  const code = await ethers.provider.getCode(await mock.getAddress());
  // The production contracts call Permit2 at its canonical address, so tests
  // install mock bytecode there instead of adding a test-only constructor arg.
  await network.provider.send("hardhat_setCode", [PERMIT2_ADDRESS, code]);
}

async function deployToken(name, symbol) {
  return deployContract("MockERC20", [name, symbol]);
}

function permitFor(token, amount, overrides = {}) {
  return {
    permitted: {
      token,
      amount,
    },
    nonce: 1,
    deadline: Math.floor(Date.now() / 1000) + 3600,
    ...overrides,
  };
}

describe("Permit2 token interactions", function () {
  let owner, user;

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners();
    await installPermit2Mock();
  });

  it("keeps the standard approve staking flow working", async function () {
    const stakingToken = await deployToken("Stake Token", "STK");
    const rewardsToken = await deployToken("Reward Token", "RWD");
    const stakingRewards = await deployContract("StakingRewards", [
      await stakingToken.getAddress(),
      await rewardsToken.getAddress(),
    ]);

    const amount = ethers.parseEther("100");
    await stakingToken.mint(user.address, amount);
    await stakingToken.connect(user).approve(await stakingRewards.getAddress(), amount);

    await stakingRewards.connect(user).stake(amount);

    expect(await stakingRewards.balanceOf(user.address)).to.equal(amount);
    expect(await stakingToken.balanceOf(await stakingRewards.getAddress())).to.equal(amount);
  });

  it("stakes with Permit2 using the canonical Permit2 address", async function () {
    const stakingToken = await deployToken("Stake Token", "STK");
    const rewardsToken = await deployToken("Reward Token", "RWD");
    const stakingRewards = await deployContract("StakingRewards", [
      await stakingToken.getAddress(),
      await rewardsToken.getAddress(),
    ]);

    const amount = ethers.parseEther("75");
    await stakingToken.mint(user.address, amount);
    await stakingToken.connect(user).approve(PERMIT2_ADDRESS, amount);

    const permit2 = await ethers.getContractAt("MockPermit2", PERMIT2_ADDRESS);
    const stakingRewardsAddress = await stakingRewards.getAddress();
    const stakingTokenAddress = await stakingToken.getAddress();

    await expect(
      stakingRewards
        .connect(user)
        .stakeWithPermit2(amount, permitFor(stakingTokenAddress, amount), SIGNATURE)
    )
      .to.emit(permit2, "PermitTransfer")
      .withArgs(stakingTokenAddress, user.address, stakingRewardsAddress, amount);

    expect(await stakingRewards.PERMIT2()).to.equal(PERMIT2_ADDRESS);
    expect(await stakingRewards.balanceOf(user.address)).to.equal(amount);
    expect(await stakingToken.balanceOf(stakingRewardsAddress)).to.equal(amount);
  });

  it("rejects Permit2 staking when the signed token or amount does not match", async function () {
    const stakingToken = await deployToken("Stake Token", "STK");
    const otherToken = await deployToken("Other Token", "OTK");
    const rewardsToken = await deployToken("Reward Token", "RWD");
    const stakingRewards = await deployContract("StakingRewards", [
      await stakingToken.getAddress(),
      await rewardsToken.getAddress(),
    ]);

    const amount = ethers.parseEther("10");
    await stakingToken.mint(user.address, amount);
    await stakingToken.connect(user).approve(PERMIT2_ADDRESS, amount);

    await expect(
      stakingRewards
        .connect(user)
        .stakeWithPermit2(amount, permitFor(await otherToken.getAddress(), amount), SIGNATURE)
    ).to.be.revertedWith("Permit token mismatch");

    await expect(
      stakingRewards
        .connect(user)
        .stakeWithPermit2(amount, permitFor(await stakingToken.getAddress(), amount - 1n), SIGNATURE)
    ).to.be.revertedWith("Permit amount too low");
  });

  it("rejects expired or empty Permit2 staking signatures", async function () {
    const stakingToken = await deployToken("Stake Token", "STK");
    const rewardsToken = await deployToken("Reward Token", "RWD");
    const stakingRewards = await deployContract("StakingRewards", [
      await stakingToken.getAddress(),
      await rewardsToken.getAddress(),
    ]);

    const amount = ethers.parseEther("10");
    const stakingTokenAddress = await stakingToken.getAddress();
    await stakingToken.mint(user.address, amount);
    await stakingToken.connect(user).approve(PERMIT2_ADDRESS, amount);

    await expect(
      stakingRewards
        .connect(user)
        .stakeWithPermit2(amount, permitFor(stakingTokenAddress, amount, { deadline: 1 }), SIGNATURE)
    ).to.be.revertedWith("Permit expired");

    await expect(
      stakingRewards
        .connect(user)
        .stakeWithPermit2(amount, permitFor(stakingTokenAddress, amount), "0x")
    ).to.be.revertedWith("Invalid signature");

    expect(await stakingRewards.balanceOf(user.address)).to.equal(0n);
    expect(await stakingToken.balanceOf(await stakingRewards.getAddress())).to.equal(0n);
  });

  it("adds AMM liquidity and swaps with Permit2 while preserving transferFrom fallback", async function () {
    const tokenA = await deployToken("Token A", "A");
    const tokenB = await deployToken("Token B", "B");
    const pool = await deployContract("AMMPool", [
      await tokenA.getAddress(),
      await tokenB.getAddress(),
    ]);

    const ownerLiquidity = ethers.parseEther("1000");
    await tokenA.mint(owner.address, ownerLiquidity);
    await tokenB.mint(owner.address, ownerLiquidity);
    await tokenA.approve(await pool.getAddress(), ownerLiquidity);
    await tokenB.approve(await pool.getAddress(), ownerLiquidity);
    await pool.addLiquidity(ownerLiquidity, ownerLiquidity);

    const swapAmount = ethers.parseEther("10");
    await tokenA.mint(user.address, swapAmount);
    await tokenA.connect(user).approve(PERMIT2_ADDRESS, swapAmount);

    const beforeTokenB = await tokenB.balanceOf(user.address);
    await pool
      .connect(user)
      .swapWithPermit2(
        await tokenA.getAddress(),
        swapAmount,
        1n,
        permitFor(await tokenA.getAddress(), swapAmount),
        SIGNATURE
      );

    const afterTokenB = await tokenB.balanceOf(user.address);
    const [reserveA, reserveB] = await pool.getReserves();
    expect(afterTokenB).to.be.gt(beforeTokenB);
    expect(reserveA).to.equal(ownerLiquidity + swapAmount);
    expect(reserveB).to.be.lt(ownerLiquidity);
  });

  it("rejects Permit2 swaps when the signature is for a different token", async function () {
    const tokenA = await deployToken("Token A", "A");
    const tokenB = await deployToken("Token B", "B");
    const pool = await deployContract("AMMPool", [
      await tokenA.getAddress(),
      await tokenB.getAddress(),
    ]);

    const liquidity = ethers.parseEther("100");
    await tokenA.mint(owner.address, liquidity);
    await tokenB.mint(owner.address, liquidity);
    await tokenA.approve(await pool.getAddress(), liquidity);
    await tokenB.approve(await pool.getAddress(), liquidity);
    await pool.addLiquidity(liquidity, liquidity);

    const swapAmount = ethers.parseEther("1");
    await tokenA.mint(user.address, swapAmount);
    await tokenA.connect(user).approve(PERMIT2_ADDRESS, swapAmount);

    await expect(
      pool
        .connect(user)
        .swapWithPermit2(
          await tokenA.getAddress(),
          swapAmount,
          1n,
          permitFor(await tokenB.getAddress(), swapAmount),
          SIGNATURE
        )
    ).to.be.revertedWith("Permit token mismatch");
  });

  it("adds AMM liquidity with Permit2", async function () {
    const tokenA = await deployToken("Token A", "A");
    const tokenB = await deployToken("Token B", "B");
    const pool = await deployContract("AMMPool", [
      await tokenA.getAddress(),
      await tokenB.getAddress(),
    ]);

    const amountA = ethers.parseEther("20");
    const amountB = ethers.parseEther("40");
    await tokenA.mint(user.address, amountA);
    await tokenB.mint(user.address, amountB);
    await tokenA.connect(user).approve(PERMIT2_ADDRESS, amountA);
    await tokenB.connect(user).approve(PERMIT2_ADDRESS, amountB);

    await pool
      .connect(user)
      .addLiquidityWithPermit2(
        amountA,
        amountB,
        permitFor(await tokenA.getAddress(), amountA),
        SIGNATURE,
        permitFor(await tokenB.getAddress(), amountB),
        SIGNATURE
      );

    const [reserveA, reserveB] = await pool.getReserves();
    expect(reserveA).to.equal(amountA);
    expect(reserveB).to.equal(amountB);
    expect(await pool.liquidity(user.address)).to.be.gt(0n);
  });

  it("deposits and repays in the lending pool with Permit2", async function () {
    const collateralToken = await deployToken("Collateral", "COL");
    const borrowToken = await deployToken("Borrow", "BRW");
    const priceFeed = await deployContract("MockPriceFeed");
    const lendingPool = await deployContract("LendingPool", [
      await priceFeed.getAddress(),
      await collateralToken.getAddress(),
      await borrowToken.getAddress(),
    ]);

    await priceFeed.setPrice(await collateralToken.getAddress(), ethers.parseEther("1"));
    await priceFeed.setPrice(await borrowToken.getAddress(), ethers.parseEther("1"));

    const collateralAmount = ethers.parseEther("200");
    const borrowAmount = ethers.parseEther("50");
    await collateralToken.mint(user.address, collateralAmount);
    await borrowToken.mint(await lendingPool.getAddress(), borrowAmount);

    await collateralToken.connect(user).approve(PERMIT2_ADDRESS, collateralAmount);
    await lendingPool
      .connect(user)
      .depositWithPermit2(
        collateralAmount,
        permitFor(await collateralToken.getAddress(), collateralAmount),
        SIGNATURE
      );

    await lendingPool.connect(user).borrow(borrowAmount);
    await borrowToken.connect(user).approve(PERMIT2_ADDRESS, borrowAmount);
    await lendingPool
      .connect(user)
      .repayWithPermit2(
        borrowAmount,
        permitFor(await borrowToken.getAddress(), borrowAmount),
        SIGNATURE
      );

    const [collateral, debt] = await lendingPool.getPosition(user.address);
    expect(collateral).to.equal(collateralAmount);
    expect(debt).to.equal(0n);
  });
});
