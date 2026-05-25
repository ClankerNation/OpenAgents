const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AMMPool minimum liquidity hardening", function () {
  let owner;
  let firstLp;
  let secondLp;
  let trader;
  let donor;
  let tokenA;
  let tokenB;
  let pool;

  const initialAmount = 1_000_000n;
  const minimumLiquidity = 1000n;

  beforeEach(async function () {
    [owner, firstLp, secondLp, trader, donor] = await ethers.getSigners();

    const MockERC20 = await ethers.getContractFactory("MockERC20");
    tokenA = await MockERC20.deploy("Token A", "TKNA");
    await tokenA.waitForDeployment();
    tokenB = await MockERC20.deploy("Token B", "TKNB");
    await tokenB.waitForDeployment();

    const AMMPool = await ethers.getContractFactory("AMMPool");
    pool = await AMMPool.deploy(await tokenA.getAddress(), await tokenB.getAddress());
    await pool.waitForDeployment();

    for (const account of [firstLp, secondLp, trader, donor]) {
      await tokenA.mint(account.address, 10_000_000n);
      await tokenB.mint(account.address, 10_000_000n);
      await tokenA.connect(account).approve(await pool.getAddress(), ethers.MaxUint256);
      await tokenB.connect(account).approve(await pool.getAddress(), ethers.MaxUint256);
    }
  });

  async function seedPool() {
    await pool.connect(firstLp).addLiquidity(initialAmount, initialAmount);
  }

  async function quoteSwap(tokenIn, amountIn) {
    const [reserveA, reserveB] = await pool.getReserves();
    const isA = tokenIn === await tokenA.getAddress();
    const reserveIn = isA ? reserveA : reserveB;
    const reserveOut = isA ? reserveB : reserveA;
    const amountInWithFee = amountIn * 9970n;
    return (amountInWithFee * reserveOut) / (reserveIn * 10000n + amountInWithFee);
  }

  it("locks 1000 LP tokens to the zero address on the first deposit", async function () {
    await expect(pool.connect(firstLp).addLiquidity(initialAmount, initialAmount))
      .to.emit(pool, "LiquidityAdded")
      .withArgs(firstLp.address, initialAmount, initialAmount, initialAmount - minimumLiquidity);

    expect(await pool.MINIMUM_LIQUIDITY()).to.equal(minimumLiquidity);
    expect(await pool.totalLiquidity()).to.equal(initialAmount);
    expect(await pool.liquidity(ethers.ZeroAddress)).to.equal(minimumLiquidity);
    expect(await pool.liquidity(firstLp.address)).to.equal(initialAmount - minimumLiquidity);
    expect(await pool.getReserves()).to.deep.equal([initialAmount, initialAmount]);
  });

  it("rejects first deposits that cannot cover the minimum liquidity lock", async function () {
    await expect(pool.connect(firstLp).addLiquidity(1000n, 1000n)).to.be.revertedWith(
      "Insufficient initial liquidity"
    );
  });

  it("uses internal reserves for removeLiquidity so passive donations do not inflate withdrawal value", async function () {
    await seedPool();
    const poolAddress = await pool.getAddress();
    const donation = 500_000n;
    await tokenA.connect(donor).transfer(poolAddress, donation);

    expect(await tokenA.balanceOf(poolAddress)).to.equal(initialAmount + donation);
    expect(await pool.getReserves()).to.deep.equal([initialAmount, initialAmount]);

    const lpTokens = await pool.liquidity(firstLp.address);
    const balanceABefore = await tokenA.balanceOf(firstLp.address);
    const balanceBBefore = await tokenB.balanceOf(firstLp.address);
    await expect(pool.connect(firstLp).removeLiquidity(lpTokens))
      .to.emit(pool, "LiquidityRemoved")
      .withArgs(firstLp.address, initialAmount - minimumLiquidity, initialAmount - minimumLiquidity);

    expect((await tokenA.balanceOf(firstLp.address)) - balanceABefore).to.equal(initialAmount - minimumLiquidity);
    expect((await tokenB.balanceOf(firstLp.address)) - balanceBBefore).to.equal(initialAmount - minimumLiquidity);
    expect(await pool.getReserves()).to.deep.equal([minimumLiquidity, minimumLiquidity]);
    expect(await pool.totalLiquidity()).to.equal(minimumLiquidity);
  });

  it("keeps swap pricing based on internal reserves until explicit sync", async function () {
    await seedPool();
    const tokenAAddress = await tokenA.getAddress();
    const poolAddress = await pool.getAddress();
    const amountIn = 10_000n;
    const quoteBeforeDonation = await quoteSwap(tokenAAddress, amountIn);

    await tokenA.connect(donor).transfer(poolAddress, 900_000n);
    const quoteAfterDonation = await quoteSwap(tokenAAddress, amountIn);

    expect(quoteAfterDonation).to.equal(quoteBeforeDonation);

    await expect(pool.connect(trader).swap(tokenAAddress, amountIn, quoteBeforeDonation))
      .to.emit(pool, "Swap")
      .withArgs(trader.address, tokenAAddress, amountIn, quoteBeforeDonation);
  });

  it("syncs internal reserves to actual balances when explicitly requested", async function () {
    await seedPool();
    const poolAddress = await pool.getAddress();
    await tokenA.connect(donor).transfer(poolAddress, 123_456n);

    await expect(pool.sync())
      .to.emit(pool, "Sync")
      .withArgs(initialAmount + 123_456n, initialAmount);

    expect(await pool.getReserves()).to.deep.equal([initialAmount + 123_456n, initialAmount]);
  });
});
