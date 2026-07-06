const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("DEX swap protections", function () {
  let tokenA, tokenB, pool, owner, trader;

  async function latestDeadline(offset = 3600) {
    const block = await ethers.provider.getBlock("latest");
    return block.timestamp + offset;
  }

  beforeEach(async function () {
    [owner, trader] = await ethers.getSigners();

    const AgentToken = await ethers.getContractFactory("AgentToken");
    tokenA = await AgentToken.deploy("Token A", "TKA", ethers.parseEther("1000000"));
    tokenB = await AgentToken.deploy("Token B", "TKB", ethers.parseEther("1000000"));

    const AMMPool = await ethers.getContractFactory("AMMPool");
    pool = await AMMPool.deploy(await tokenA.getAddress(), await tokenB.getAddress());

    await tokenA.approve(await pool.getAddress(), ethers.parseEther("10000"));
    await tokenB.approve(await pool.getAddress(), ethers.parseEther("10000"));
    await pool.addLiquidity(ethers.parseEther("10000"), ethers.parseEther("10000"));

    await tokenA.mint(trader.address, ethers.parseEther("1000"));
    await tokenA.connect(trader).approve(await pool.getAddress(), ethers.parseEther("1000"));
  });

  it("reverts when output is below minAmountOut", async function () {
    await expect(
      pool.connect(trader).swap(
        await tokenA.getAddress(),
        ethers.parseEther("1"),
        ethers.parseEther("100"),
        await latestDeadline()
      )
    ).to.be.revertedWith("Slippage exceeded");
  });

  it("reverts when deadline has expired", async function () {
    await expect(
      pool.connect(trader).swap(
        await tokenA.getAddress(),
        ethers.parseEther("1"),
        0,
        1
      )
    ).to.be.revertedWith("Deadline expired");
  });

  it("charges at least 1 wei of fee on tiny swaps", async function () {
    const quoteWithMinimumFee = await pool.connect(trader).swap.staticCall(
      await tokenA.getAddress(),
      2,
      0,
      await latestDeadline()
    );

    expect(quoteWithMinimumFee).to.equal(0n);
  });
});
