const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AMMPool", function () {
  async function deployFixture() {
    const [owner, firstLp, secondLp, donor] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("MockERC20");
    const tokenA = await Token.deploy("Token A", "TKA");
    const tokenB = await Token.deploy("Token B", "TKB");
    await tokenA.waitForDeployment();
    await tokenB.waitForDeployment();

    const Pool = await ethers.getContractFactory("AMMPoolHarness");
    const pool = await Pool.deploy(await tokenA.getAddress(), await tokenB.getAddress());
    await pool.waitForDeployment();

    return { owner, firstLp, secondLp, donor, tokenA, tokenB, pool };
  }

  async function fundAndApprove(tokenA, tokenB, pool, signer, amountA, amountB) {
    const poolAddress = await pool.getAddress();
    await tokenA.mint(signer.address, amountA);
    await tokenB.mint(signer.address, amountB);
    await tokenA.connect(signer).approve(poolAddress, amountA);
    await tokenB.connect(signer).approve(poolAddress, amountB);
  }

  it("locks minimum liquidity on the first deposit", async function () {
    const { firstLp, tokenA, tokenB, pool } = await deployFixture();
    const amount = 10_000n;

    await fundAndApprove(tokenA, tokenB, pool, firstLp, amount, amount);

    await expect(pool.connect(firstLp).addLiquidity(amount, amount))
      .to.emit(pool, "LiquidityAdded")
      .withArgs(firstLp.address, amount, amount, amount - 1000n);

    expect(await pool.MINIMUM_LIQUIDITY()).to.equal(1000);
    expect(await pool.totalLiquidity()).to.equal(amount);
    expect(await pool.liquidity(ethers.ZeroAddress)).to.equal(1000);
    expect(await pool.liquidity(firstLp.address)).to.equal(amount - 1000n);
  });

  it("uses internal reserves when removing liquidity after direct donations", async function () {
    const { firstLp, donor, tokenA, tokenB, pool } = await deployFixture();
    const amount = 10_000n;
    const poolAddress = await pool.getAddress();

    await fundAndApprove(tokenA, tokenB, pool, firstLp, amount, amount);
    await pool.connect(firstLp).addLiquidity(amount, amount);

    await tokenA.mint(donor.address, 5_000n);
    await tokenA.connect(donor).transfer(poolAddress, 5_000n);

    expect(await tokenA.balanceOf(poolAddress)).to.equal(15_000n);
    expect(await pool.reserveA()).to.equal(10_000n);

    await pool.connect(firstLp).removeLiquidity(9_000n);

    expect(await tokenA.balanceOf(firstLp.address)).to.equal(9_000n);
    expect(await tokenB.balanceOf(firstLp.address)).to.equal(9_000n);
    expect(await pool.reserveA()).to.equal(1_000n);
    expect(await pool.reserveB()).to.equal(1_000n);
    expect(await tokenA.balanceOf(poolAddress)).to.equal(6_000n);
  });

  it("prices later liquidity from internal reserves rather than donated balances", async function () {
    const { firstLp, secondLp, donor, tokenA, tokenB, pool } = await deployFixture();
    const poolAddress = await pool.getAddress();

    await fundAndApprove(tokenA, tokenB, pool, firstLp, 10_000n, 10_000n);
    await pool.connect(firstLp).addLiquidity(10_000n, 10_000n);

    await tokenA.mint(donor.address, 5_000n);
    await tokenA.connect(donor).transfer(poolAddress, 5_000n);

    await fundAndApprove(tokenA, tokenB, pool, secondLp, 1_000n, 1_000n);
    await pool.connect(secondLp).addLiquidity(1_000n, 1_000n);

    expect(await pool.liquidity(secondLp.address)).to.equal(1_000n);
    expect(await pool.reserveA()).to.equal(11_000n);
    expect(await pool.reserveB()).to.equal(11_000n);
  });

  it("syncs reserves to actual balances when explicitly requested", async function () {
    const { firstLp, donor, tokenA, tokenB, pool } = await deployFixture();
    const poolAddress = await pool.getAddress();

    await fundAndApprove(tokenA, tokenB, pool, firstLp, 10_000n, 10_000n);
    await pool.connect(firstLp).addLiquidity(10_000n, 10_000n);

    await tokenA.mint(donor.address, 5_000n);
    await tokenA.connect(donor).transfer(poolAddress, 5_000n);

    await expect(pool.sync()).to.emit(pool, "Sync").withArgs(15_000n, 10_000n);
    expect(await pool.reserveA()).to.equal(15_000n);
    expect(await pool.reserveB()).to.equal(10_000n);
  });
});
