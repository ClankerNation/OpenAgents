const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AMMPool indexer events", function () {
  let owner, liquidityProvider, trader;
  let tokenA, tokenB, pool;
  let tokenAAddress, tokenBAddress, poolAddress;

  const initialSupply = ethers.parseEther("1000000");
  const liquidityAmount = ethers.parseEther("1000");

  beforeEach(async function () {
    [owner, liquidityProvider, trader] = await ethers.getSigners();

    const AgentToken = await ethers.getContractFactory("AgentToken");
    tokenA = await AgentToken.deploy("Token A", "TKNA", initialSupply);
    tokenB = await AgentToken.deploy("Token B", "TKNB", initialSupply);
    await tokenA.waitForDeployment();
    await tokenB.waitForDeployment();

    tokenAAddress = await tokenA.getAddress();
    tokenBAddress = await tokenB.getAddress();

    const AMMPool = await ethers.getContractFactory("AMMPool");
    pool = await AMMPool.deploy(tokenAAddress, tokenBAddress);
    await pool.waitForDeployment();
    poolAddress = await pool.getAddress();

    await tokenA.transfer(liquidityProvider.address, ethers.parseEther("2000"));
    await tokenB.transfer(liquidityProvider.address, ethers.parseEther("2000"));
    await tokenA.transfer(trader.address, ethers.parseEther("100"));

    await tokenA.connect(liquidityProvider).approve(poolAddress, ethers.MaxUint256);
    await tokenB.connect(liquidityProvider).approve(poolAddress, ethers.MaxUint256);
    await tokenA.connect(trader).approve(poolAddress, ethers.MaxUint256);
  });

  it("indexes Swap user and tokenIn fields for log filtering", async function () {
    const swapEvent = pool.interface.getEvent("Swap");

    expect(swapEvent.inputs[0].name).to.equal("user");
    expect(swapEvent.inputs[0].indexed).to.equal(true);
    expect(swapEvent.inputs[1].name).to.equal("tokenIn");
    expect(swapEvent.inputs[1].indexed).to.equal(true);
  });

  it("emits Mint and Sync when liquidity is added", async function () {
    const tx = await pool.connect(liquidityProvider).addLiquidity(liquidityAmount, liquidityAmount);

    await expect(tx)
      .to.emit(pool, "Mint")
      .withArgs(liquidityProvider.address, liquidityAmount, liquidityAmount);

    await expect(tx)
      .to.emit(pool, "Sync")
      .withArgs(liquidityAmount, liquidityAmount);
  });

  it("emits Burn and Sync when liquidity is removed", async function () {
    await pool.connect(liquidityProvider).addLiquidity(liquidityAmount, liquidityAmount);

    const burnedLiquidity = ethers.parseEther("500");
    const tx = await pool.connect(liquidityProvider).removeLiquidity(burnedLiquidity);

    await expect(tx)
      .to.emit(pool, "Burn")
      .withArgs(liquidityProvider.address, burnedLiquidity, burnedLiquidity, liquidityProvider.address);

    await expect(tx)
      .to.emit(pool, "Sync")
      .withArgs(liquidityAmount - burnedLiquidity, liquidityAmount - burnedLiquidity);
  });

  it("emits indexed Swap and updated Sync reserves after swaps", async function () {
    await pool.connect(liquidityProvider).addLiquidity(liquidityAmount, liquidityAmount);

    const amountIn = ethers.parseEther("10");
    const amountInWithFee = amountIn * 9970n;
    const amountOut = (amountInWithFee * liquidityAmount) / (liquidityAmount * 10000n + amountInWithFee);

    const tx = await pool.connect(trader).swap(tokenAAddress, amountIn, 0);

    await expect(tx)
      .to.emit(pool, "Swap")
      .withArgs(trader.address, tokenAAddress, amountIn, amountOut);

    await expect(tx)
      .to.emit(pool, "Sync")
      .withArgs(liquidityAmount + amountIn, liquidityAmount - amountOut);
  });
});
