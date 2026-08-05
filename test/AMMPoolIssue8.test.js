const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AMMPool inflation protection", function () {
  async function deployFixture() {
    const [provider, trader, donor] = await ethers.getSigners();
    const Token = await ethers.getContractFactory("AMMPoolTestToken");
    const tokenA = await Token.deploy("Token A", "TKA");
    const tokenB = await Token.deploy("Token B", "TKB");
    await Promise.all([tokenA.waitForDeployment(), tokenB.waitForDeployment()]);

    const Pool = await ethers.getContractFactory("AMMPool");
    const pool = await Pool.deploy(await tokenA.getAddress(), await tokenB.getAddress());
    await pool.waitForDeployment();

    return { provider, trader, donor, tokenA, tokenB, pool };
  }

  async function addInitialLiquidity(tokenA, tokenB, pool, provider, amount = 1_000_000n) {
    await tokenA.mint(provider.address, amount);
    await tokenB.mint(provider.address, amount);
    await tokenA.connect(provider).approve(await pool.getAddress(), amount);
    await tokenB.connect(provider).approve(await pool.getAddress(), amount);
    await pool.connect(provider).addLiquidity(amount, amount);
  }

  function quote(amountIn, reserveIn, reserveOut) {
    const amountInWithFee = amountIn * 9970n;
    return (amountInWithFee * reserveOut) / (reserveIn * 10000n + amountInWithFee);
  }

  it("locks minimum liquidity on the first deposit", async function () {
    const { provider, tokenA, tokenB, pool } = await deployFixture();

    await addInitialLiquidity(tokenA, tokenB, pool, provider);

    expect(await pool.MINIMUM_LIQUIDITY()).to.equal(1000n);
    expect(await pool.liquidity(ethers.ZeroAddress)).to.equal(1000n);
    expect(await pool.liquidity(provider.address)).to.equal(999000n);
    expect(await pool.totalLiquidity()).to.equal(1000000n);
    await expect(pool.connect(provider).removeLiquidity(1000000n)).to.be.revertedWith(
      "Invalid amount"
    );
  });

  it("rejects a first deposit that cannot leave the locked liquidity", async function () {
    const { provider, tokenA, tokenB, pool } = await deployFixture();
    await tokenA.mint(provider.address, 1000n);
    await tokenB.mint(provider.address, 1000n);
    await tokenA.connect(provider).approve(await pool.getAddress(), 1000n);
    await tokenB.connect(provider).approve(await pool.getAddress(), 1000n);

    await expect(pool.connect(provider).addLiquidity(1000n, 1000n)).to.be.revertedWith(
      "Insufficient liquidity"
    );
  });

  it("keeps direct donations out of pricing until sync", async function () {
    const { provider, trader, donor, tokenA, tokenB, pool } = await deployFixture();
    await addInitialLiquidity(tokenA, tokenB, pool, provider);

    await tokenB.mint(donor.address, 1_000_000n);
    await tokenB.connect(donor).transfer(await pool.getAddress(), 1_000_000n);
    expect(await pool.getReserves()).to.deep.equal([1000000n, 1000000n]);

    const amountIn = 10_000n;
    const expectedOut = quote(amountIn, 1_000_000n, 1_000_000n);
    await tokenA.mint(trader.address, amountIn);
    await tokenA.connect(trader).approve(await pool.getAddress(), amountIn);
    await pool.connect(trader).swap(await tokenA.getAddress(), amountIn, expectedOut);

    expect(await tokenB.balanceOf(trader.address)).to.equal(expectedOut);
  });

  it("uses internal reserves for removal despite direct donations", async function () {
    const { provider, donor, tokenA, tokenB, pool } = await deployFixture();
    await addInitialLiquidity(tokenA, tokenB, pool, provider);

    await tokenA.mint(donor.address, 1_000_000n);
    await tokenA.connect(donor).transfer(await pool.getAddress(), 1_000_000n);

    await pool.connect(provider).removeLiquidity(999000n);
    expect(await tokenA.balanceOf(provider.address)).to.equal(999000n);
    expect(await tokenB.balanceOf(provider.address)).to.equal(999000n);
    expect(await pool.getReserves()).to.deep.equal([1000n, 1000n]);
  });

  it("reconciles reserves only when sync is explicitly called", async function () {
    const { provider, donor, tokenA, tokenB, pool } = await deployFixture();
    await addInitialLiquidity(tokenA, tokenB, pool, provider);

    await tokenA.mint(donor.address, 123n);
    await tokenA.connect(donor).transfer(await pool.getAddress(), 123n);
    await pool.sync();

    expect(await pool.getReserves()).to.deep.equal([1000123n, 1000000n]);
  });
});
