const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AMMPool swap protections", function () {
  let pool;
  let tokenA;
  let tokenB;
  let owner;
  let trader;

  const INITIAL_LIQUIDITY = ethers.parseEther("1000");
  const SWAP_AMOUNT = ethers.parseEther("10");

  beforeEach(async function () {
    [owner, trader] = await ethers.getSigners();

    const AMMPoolTestToken = await ethers.getContractFactory("AMMPoolTestToken");
    tokenA = await AMMPoolTestToken.deploy("Token A", "TKNA");
    tokenB = await AMMPoolTestToken.deploy("Token B", "TKNB");
    await tokenA.waitForDeployment();
    await tokenB.waitForDeployment();

    const AMMPool = await ethers.getContractFactory("AMMPool");
    pool = await AMMPool.deploy(await tokenA.getAddress(), await tokenB.getAddress());
    await pool.waitForDeployment();

    await tokenA.mint(owner.address, INITIAL_LIQUIDITY);
    await tokenB.mint(owner.address, INITIAL_LIQUIDITY);
    await tokenA.mint(trader.address, ethers.parseEther("100"));
    await tokenB.mint(trader.address, ethers.parseEther("100"));

    await tokenA.approve(await pool.getAddress(), INITIAL_LIQUIDITY);
    await tokenB.approve(await pool.getAddress(), INITIAL_LIQUIDITY);
    await pool.addLiquidity(INITIAL_LIQUIDITY, INITIAL_LIQUIDITY);
  });

  async function futureDeadline() {
    const latest = await ethers.provider.getBlock("latest");
    return BigInt(latest.timestamp + 3600);
  }

  it("reverts when output is below minAmountOut", async function () {
    await tokenA.connect(trader).approve(await pool.getAddress(), SWAP_AMOUNT);
    const [quotedOut] = await pool.getAmountOut(await tokenA.getAddress(), SWAP_AMOUNT);

    await expect(
      pool.connect(trader).swap(
        await tokenA.getAddress(),
        SWAP_AMOUNT,
        quotedOut + 1n,
        await futureDeadline()
      )
    ).to.be.revertedWith("Slippage exceeded");
  });

  it("reverts when the deadline has passed", async function () {
    await tokenA.connect(trader).approve(await pool.getAddress(), SWAP_AMOUNT);
    const [quotedOut] = await pool.getAmountOut(await tokenA.getAddress(), SWAP_AMOUNT);
    const latest = await ethers.provider.getBlock("latest");

    await expect(
      pool.connect(trader).swap(
        await tokenA.getAddress(),
        SWAP_AMOUNT,
        quotedOut,
        latest.timestamp - 1
      )
    ).to.be.revertedWith("Swap expired");
  });

  it("charges at least a 1 wei fee for tiny swaps", async function () {
    const tinyAmount = 100n;
    await tokenA.connect(trader).approve(await pool.getAddress(), tinyAmount);
    const [quotedOut, fee] = await pool.getAmountOut(await tokenA.getAddress(), tinyAmount);

    expect(fee).to.equal(1n);

    await expect(
      pool.connect(trader).swap(
        await tokenA.getAddress(),
        tinyAmount,
        quotedOut,
        await futureDeadline()
      )
    )
      .to.emit(pool, "Swap")
      .withArgs(trader.address, await tokenA.getAddress(), tinyAmount, quotedOut, 1n);
  });

  it("executes when minAmountOut and deadline are satisfied", async function () {
    await tokenA.connect(trader).approve(await pool.getAddress(), SWAP_AMOUNT);
    const [quotedOut] = await pool.getAmountOut(await tokenA.getAddress(), SWAP_AMOUNT);
    const traderTokenBBefore = await tokenB.balanceOf(trader.address);

    await pool.connect(trader).swap(
      await tokenA.getAddress(),
      SWAP_AMOUNT,
      quotedOut,
      await futureDeadline()
    );

    expect(await tokenB.balanceOf(trader.address)).to.equal(traderTokenBBefore + quotedOut);
  });
});
