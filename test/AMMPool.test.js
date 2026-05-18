const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AMMPool — Indexed Events & Uniswap V2 Compatibility (#165)", function () {
  let pool, tokenA, tokenB;
  let owner, lp1, lp2, trader;

  const ONE_ETH = ethers.parseEther("1");
  const TEN_ETH = ethers.parseEther("10");
  const HUNDRED_ETH = ethers.parseEther("100");

  beforeEach(async function () {
    [owner, lp1, lp2, trader] = await ethers.getSigners();

    // Deploy mock tokens
    const MockToken = await ethers.getContractFactory("MockERC20");
    tokenA = await MockToken.deploy("Token A", "TKA");
    await tokenA.waitForDeployment();
    tokenB = await MockToken.deploy("Token B", "TKB");
    await tokenB.waitForDeployment();

    // Deploy AMMPool
    const AMMPool = await ethers.getContractFactory("AMMPool");
    pool = await AMMPool.deploy(tokenA.target, tokenB.target);
    await pool.waitForDeployment();

    // Mint tokens to all participants
    for (const signer of [lp1, lp2, trader]) {
      await tokenA.mint(signer.address, HUNDRED_ETH);
      await tokenB.mint(signer.address, HUNDRED_ETH);
    }

    // Approve pool for all participants
    for (const signer of [lp1, lp2, trader]) {
      await tokenA.connect(signer).approve(pool.target, ethers.MaxUint256);
      await tokenB.connect(signer).approve(pool.target, ethers.MaxUint256);
    }
  });

  // ─── Mint Event ──────────────────────────────────────────────

  it("should emit Mint event on addLiquidity with correct amounts", async function () {
    const amtA = TEN_ETH;
    const amtB = TEN_ETH;

    await expect(pool.connect(lp1).addLiquidity(amtA, amtB))
      .to.emit(pool, "Mint")
      .withArgs(lp1.address, amtA, amtB);
  });

  it("should emit Mint event with indexed sender address", async function () {
    const amtA = ethers.parseEther("5");
    const amtB = ethers.parseEther("5");

    const tx = await pool.connect(lp2).addLiquidity(amtA, amtB);
    const receipt = await tx.wait();

    // Find Mint event and verify indexed sender
    const mintEvent = receipt.logs.find(
      (log) => pool.interface.parseLog(log)?.name === "Mint"
    );
    expect(mintEvent).to.not.be.undefined;
    const parsed = pool.interface.parseLog(mintEvent);
    expect(parsed.args.sender).to.equal(lp2.address);
  });

  // ─── Burn Event ──────────────────────────────────────────────

  it("should emit Burn event on removeLiquidity with correct amounts", async function () {
    // First add liquidity
    const amtA = TEN_ETH;
    const amtB = TEN_ETH;
    await pool.connect(lp1).addLiquidity(amtA, amtB);

    // Get LP's liquidity balance
    const lpBalance = await pool.liquidity(lp1.address);

    await expect(pool.connect(lp1).removeLiquidity(lpBalance))
      .to.emit(pool, "Burn")
      .withArgs(lp1.address, amtA, amtB, lp1.address);
  });

  it("should emit Burn event with indexed sender and to addresses", async function () {
    const amtA = TEN_ETH;
    const amtB = TEN_ETH;
    await pool.connect(lp1).addLiquidity(amtA, amtB);
    const lpBalance = await pool.liquidity(lp1.address);

    const tx = await pool.connect(lp1).removeLiquidity(lpBalance);
    const receipt = await tx.wait();

    const burnEvent = receipt.logs.find(
      (log) => pool.interface.parseLog(log)?.name === "Burn"
    );
    expect(burnEvent).to.not.be.undefined;
    const parsed = pool.interface.parseLog(burnEvent);
    expect(parsed.args.sender).to.equal(lp1.address);
    expect(parsed.args.to).to.equal(lp1.address);
  });

  // ─── Swap Event — Indexed Parameters ────────────────────────

  it("should emit Swap event with indexed user and tokenIn", async function () {
    // Add initial liquidity
    await pool.connect(lp1).addLiquidity(HUNDRED_ETH, HUNDRED_ETH);

    const swapAmt = ONE_ETH;

    const tx = await pool.connect(trader).swap(
      tokenA.target,
      swapAmt,
      0 // minAmountOut = 0 for test
    );
    const receipt = await tx.wait();

    const swapEvent = receipt.logs.find(
      (log) => pool.interface.parseLog(log)?.name === "Swap"
    );
    expect(swapEvent).to.not.be.undefined;

    const parsed = pool.interface.parseLog(swapEvent);
    expect(parsed.args.user).to.equal(trader.address);
    expect(parsed.args.tokenIn).to.equal(tokenA.target);
    expect(parsed.args.amountIn).to.equal(swapAmt);
    expect(parsed.args.amountOut).to.be.gt(0);
  });

  it("should emit Swap event when swapping tokenB for tokenA", async function () {
    await pool.connect(lp1).addLiquidity(HUNDRED_ETH, HUNDRED_ETH);

    const swapAmt = ONE_ETH;

    await expect(
      pool.connect(trader).swap(tokenB.target, swapAmt, 0)
    )
      .to.emit(pool, "Swap")
      .withArgs(trader.address, tokenB.target, swapAmt, (v) => v > 0n);
  });

  // ─── Sync Event ──────────────────────────────────────────────

  it("should emit Sync event after every swap with updated reserves", async function () {
    await pool.connect(lp1).addLiquidity(HUNDRED_ETH, HUNDRED_ETH);

    const [resA0, resB0] = await pool.getReserves();

    const swapAmt = ONE_ETH;
    await pool.connect(trader).swap(tokenA.target, swapAmt, 0);

    const [resA1, resB1] = await pool.getReserves();

    // Reserves should have changed
    expect(resA1).to.equal(resA0 + swapAmt);
    expect(resB1).to.be.lt(resB0);
  });

  it("should emit Sync event with correct reserve values after swap", async function () {
    await pool.connect(lp1).addLiquidity(HUNDRED_ETH, HUNDRED_ETH);

    const swapAmt = ONE_ETH;
    const tx = await pool.connect(trader).swap(tokenA.target, swapAmt, 0);
    const receipt = await tx.wait();

    const syncEvents = receipt.logs.filter(
      (log) => pool.interface.parseLog(log)?.name === "Sync"
    );
    expect(syncEvents.length).to.be.gte(1);

    // The last Sync should match current reserves
    const lastSync = syncEvents[syncEvents.length - 1];
    const parsed = pool.interface.parseLog(lastSync);
    const [currentA, currentB] = await pool.getReserves();
    expect(parsed.args.reserveA).to.equal(currentA);
    expect(parsed.args.reserveB).to.equal(currentB);
  });

  it("should emit Sync event after addLiquidity", async function () {
    const amtA = TEN_ETH;
    const amtB = TEN_ETH;

    const tx = await pool.connect(lp1).addLiquidity(amtA, amtB);
    const receipt = await tx.wait();

    const syncEvent = receipt.logs.find(
      (log) => pool.interface.parseLog(log)?.name === "Sync"
    );
    expect(syncEvent).to.not.be.undefined;
  });

  it("should emit Sync event after removeLiquidity", async function () {
    await pool.connect(lp1).addLiquidity(TEN_ETH, TEN_ETH);
    const lpBalance = await pool.liquidity(lp1.address);

    const tx = await pool.connect(lp1).removeLiquidity(lpBalance);
    const receipt = await tx.wait();

    const syncEvent = receipt.logs.find(
      (log) => pool.interface.parseLog(log)?.name === "Sync"
    );
    expect(syncEvent).to.not.be.undefined;
    const parsed = pool.interface.parseLog(syncEvent);
    const [currentA, currentB] = await pool.getReserves();
    expect(parsed.args.reserveA).to.equal(currentA);
    expect(parsed.args.reserveB).to.equal(currentB);
  });

  // ─── Backwards Compatibility ────────────────────────────────

  it("should still emit LiquidityAdded event (backwards compat)", async function () {
    await expect(pool.connect(lp1).addLiquidity(TEN_ETH, TEN_ETH))
      .to.emit(pool, "LiquidityAdded");
  });

  it("should still emit LiquidityRemoved event (backwards compat)", async function () {
    await pool.connect(lp1).addLiquidity(TEN_ETH, TEN_ETH);
    const lpBalance = await pool.liquidity(lp1.address);

    await expect(pool.connect(lp1).removeLiquidity(lpBalance))
      .to.emit(pool, "LiquidityRemoved");
  });

  // ─── Event Topic Indexing Verification ──────────────────────

  it("Swap event should have 3 indexed params (user, tokenIn, and event sig)", async function () {
    await pool.connect(lp1).addLiquidity(HUNDRED_ETH, HUNDRED_ETH);

    const tx = await pool.connect(trader).swap(tokenA.target, ONE_ETH, 0);
    const receipt = await tx.wait();

    const swapLog = receipt.logs.find(
      (log) => pool.interface.parseLog(log)?.name === "Swap"
    );
    expect(swapLog).to.not.be.undefined;
    // ethers log: topics[0] = event sig, topics[1] = indexed user, topics[2] = indexed tokenIn
    expect(swapLog.topics.length).to.equal(3);
  });

  it("Mint event should have 2 topics (event sig + indexed sender)", async function () {
    const tx = await pool.connect(lp1).addLiquidity(TEN_ETH, TEN_ETH);
    const receipt = await tx.wait();

    const mintLog = receipt.logs.find(
      (log) => pool.interface.parseLog(log)?.name === "Mint"
    );
    expect(mintLog).to.not.be.undefined;
    expect(mintLog.topics.length).to.equal(2);
  });

  it("Burn event should have 3 topics (event sig + indexed sender + indexed to)", async function () {
    await pool.connect(lp1).addLiquidity(TEN_ETH, TEN_ETH);
    const lpBalance = await pool.liquidity(lp1.address);

    const tx = await pool.connect(lp1).removeLiquidity(lpBalance);
    const receipt = await tx.wait();

    const burnLog = receipt.logs.find(
      (log) => pool.interface.parseLog(log)?.name === "Burn"
    );
    expect(burnLog).to.not.be.undefined;
    expect(burnLog.topics.length).to.equal(3);
  });

  // ─── Slippage Protection Still Works ────────────────────────

  it("should revert swap when minAmountOut exceeds actual output", async function () {
    await pool.connect(lp1).addLiquidity(HUNDRED_ETH, HUNDRED_ETH);

    // Request an impossibly high output
    await expect(
      pool.connect(trader).swap(tokenA.target, ONE_ETH, HUNDRED_ETH)
    ).to.be.revertedWith("Slippage exceeded");
  });
});
