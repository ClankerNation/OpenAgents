const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("SimpleSwap / AMMPool - Issue #5 fix: slippage + deadline + fee floor", function () {
  let tokenA, tokenB, pool, simpleSwap;
  let owner, user;

  async function deployMockToken(name, symbol) {
    const Factory = await ethers.getContractFactory("AgentToken");
    const token = await Factory.deploy(name, symbol, ethers.parseEther("1000000"));
    await token.waitForDeployment();
    return token;
  }

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners();
    tokenA = await deployMockToken("TokenA", "TKA");
    tokenB = await deployMockToken("TokenB", "TKB");

    const AMMPool = await ethers.getContractFactory("AMMPool");
    pool = await AMMPool.deploy(await tokenA.getAddress(), await tokenB.getAddress());
    await pool.waitForDeployment();

    const SimpleSwap = await ethers.getContractFactory("SimpleSwap");
    simpleSwap = await SimpleSwap.deploy(await tokenA.getAddress(), await tokenB.getAddress());
    await simpleSwap.waitForDeployment();

    const liq = ethers.parseEther("10000");
    await tokenA.approve(await pool.getAddress(), liq);
    await tokenB.approve(await pool.getAddress(), liq);
    await pool.addLiquidity(liq, liq);

    await tokenA.approve(await simpleSwap.getAddress(), liq);
    await tokenB.approve(await simpleSwap.getAddress(), liq);
    await simpleSwap.addLiquidity(liq, liq);

    await tokenA.transfer(user.address, ethers.parseEther("1000"));
    await tokenB.transfer(user.address, ethers.parseEther("1000"));
  });

  function futureDeadline() {
    return Math.floor(Date.now() / 1000) + 3600;
  }
  function pastDeadline() {
    return Math.floor(Date.now() / 1000) - 3600;
  }

  describe("AC1: Swap reverts when output below minAmountOut (slippage)", function () {
    it("SimpleSwap 4-arg: reverts on slippage", async function () {
      const amountIn = ethers.parseEther("100");
      const tokenAAddr = await tokenA.getAddress();
      const expected = await simpleSwap.getAmountOut(tokenAAddr, amountIn);
      const tooHigh = expected + 1n;
      await tokenA.connect(user).approve(await simpleSwap.getAddress(), amountIn);
      await expect(
        simpleSwap.connect(user)["swap(address,uint256,uint256,uint256)"](tokenAAddr, amountIn, tooHigh, futureDeadline())
      ).to.be.revertedWith("Slippage exceeded");
    });

    it("SimpleSwap 3-arg backward compat: reverts on slippage", async function () {
      const amountIn = ethers.parseEther("50");
      const tokenAAddr = await tokenA.getAddress();
      const expected = await simpleSwap.getAmountOut(tokenAAddr, amountIn);
      await tokenA.connect(user).approve(await simpleSwap.getAddress(), amountIn);
      await expect(
        simpleSwap.connect(user)["swap(address,uint256,uint256)"](tokenAAddr, amountIn, expected + 1n)
      ).to.be.revertedWith("Slippage exceeded");
    });

    it("AMMPool 4-arg: reverts on slippage", async function () {
      const amountIn = ethers.parseEther("100");
      const tokenAAddr = await tokenA.getAddress();
      const expected = await pool.getAmountOut(tokenAAddr, amountIn);
      await tokenA.connect(user).approve(await pool.getAddress(), amountIn);
      await expect(
        pool.connect(user)["swap(address,uint256,uint256,uint256)"](tokenAAddr, amountIn, expected + 1n, futureDeadline())
      ).to.be.revertedWith("Slippage exceeded");
    });

    it("AMMPool 3-arg: reverts on slippage", async function () {
      const amountIn = ethers.parseEther("100");
      const tokenAAddr = await tokenA.getAddress();
      const expected = await pool.getAmountOut(tokenAAddr, amountIn);
      await tokenA.connect(user).approve(await pool.getAddress(), amountIn);
      await expect(
        pool.connect(user)["swap(address,uint256,uint256)"](tokenAAddr, amountIn, expected + 1n)
      ).to.be.revertedWith("Slippage exceeded");
    });

    it("succeeds when minAmountOut is achievable", async function () {
      const amountIn = ethers.parseEther("10");
      const tokenAAddr = await tokenA.getAddress();
      const expected = await simpleSwap.getAmountOut(tokenAAddr, amountIn);
      await tokenA.connect(user).approve(await simpleSwap.getAddress(), amountIn);
      await expect(
        simpleSwap.connect(user)["swap(address,uint256,uint256,uint256)"](tokenAAddr, amountIn, expected, futureDeadline())
      ).to.not.be.reverted;
    });
  });

  describe("AC2: Swap reverts when past deadline", function () {
    it("SimpleSwap reverts when block.timestamp > deadline", async function () {
      const amountIn = ethers.parseEther("10");
      await tokenA.connect(user).approve(await simpleSwap.getAddress(), amountIn);
      await expect(
        simpleSwap.connect(user)["swap(address,uint256,uint256,uint256)"](await tokenA.getAddress(), amountIn, 0, pastDeadline())
      ).to.be.revertedWith("Deadline expired");
    });

    it("AMMPool reverts when past deadline", async function () {
      const amountIn = ethers.parseEther("10");
      await tokenA.connect(user).approve(await pool.getAddress(), amountIn);
      await expect(
        pool.connect(user)["swap(address,uint256,uint256,uint256)"](await tokenA.getAddress(), amountIn, 0, pastDeadline())
      ).to.be.revertedWith("Deadline expired");
    });

    it("deadline in future passes", async function () {
      const amountIn = ethers.parseEther("1");
      await tokenA.connect(user).approve(await simpleSwap.getAddress(), amountIn);
      await expect(
        simpleSwap.connect(user)["swap(address,uint256,uint256,uint256)"](await tokenA.getAddress(), amountIn, 0, futureDeadline())
      ).to.not.be.reverted;
    });
  });

  describe("AC3: Fee >= 1 wei always", function () {
    it("tiny swap fee is at least 1 wei (amountIn=100)", async function () {
      const amountIn2 = 100n;
      const tokenAAddr = await tokenA.getAddress();
      const quote = await simpleSwap.getAmountOut(tokenAAddr, amountIn2);
      expect(quote).to.be.gt(0);
      const quotePool = await pool.getAmountOut(tokenAAddr, amountIn2);
      expect(quotePool).to.be.gt(0);
      expect(quote).to.equal(quotePool);
    });

    it("amountIn=1 on SimpleSwap reverts Insufficient output (fee eats all, proves floor)", async function () {
      await tokenA.connect(user).approve(await simpleSwap.getAddress(), 1);
      await expect(
        simpleSwap.connect(user)["swap(address,uint256,uint256,uint256)"](await tokenA.getAddress(), 1, 0, futureDeadline())
      ).to.be.revertedWith("Insufficient output");
    });

    it("fee for 333 wei is 1 wei (would have been 0)", async function () {
      const quote333 = await simpleSwap.getAmountOut(await tokenA.getAddress(), 333);
      const quote332 = await simpleSwap.getAmountOut(await tokenA.getAddress(), 332);
      expect(quote333).to.be.gte(quote332);
      expect(quote333).to.be.gt(0);
    });

    it("normal amount fee is proportional (10000 wei => fee 30)", async function () {
      const amountIn = 10000n;
      const fee = (amountIn * 30n) / 10000n;
      expect(fee).to.equal(30n);
      const quote = await simpleSwap.getAmountOut(await tokenA.getAddress(), amountIn);
      expect(quote).to.be.gt(0);
    });

    it("actual swap with amountIn=100 wei succeeds and reserves update", async function () {
      const amountIn = 100n;
      await tokenA.connect(user).approve(await simpleSwap.getAddress(), amountIn);
      const before = await simpleSwap.getReserves();
      await simpleSwap.connect(user)["swap(address,uint256,uint256,uint256)"](await tokenA.getAddress(), amountIn, 0, futureDeadline());
      const after = await simpleSwap.getReserves();
      expect(after[0]).to.equal(before[0] + amountIn);
    });
  });
});
