const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AMMPool", function () {
  let tokenA, tokenB, ammPool;
  let owner, user1;

  beforeEach(async function () {
    [owner, user1] = await ethers.getSigners();

    // Deploy two mock AgentTokens (ERC20)
    const AgentToken = await ethers.getContractFactory("AgentToken");
    tokenA = await AgentToken.deploy("Token A", "TKNA", ethers.parseEther("1000000"));
    await tokenA.waitForDeployment();

    tokenB = await AgentToken.deploy("Token B", "TKNB", ethers.parseEther("1000000"));
    await tokenB.waitForDeployment();

    // Deploy AMMPool
    const AMMPool = await ethers.getContractFactory("AMMPool");
    ammPool = await AMMPool.deploy(await tokenA.getAddress(), await tokenB.getAddress());
    await ammPool.waitForDeployment();

    // Approve tokens for Owner and User1
    const approveAmount = ethers.parseEther("100000");
    await tokenA.approve(await ammPool.getAddress(), approveAmount);
    await tokenB.approve(await ammPool.getAddress(), approveAmount);

    await tokenA.mint(user1.address, approveAmount);
    await tokenB.mint(user1.address, approveAmount);

    await tokenA.connect(user1).approve(await ammPool.getAddress(), approveAmount);
    await tokenB.connect(user1).approve(await ammPool.getAddress(), approveAmount);
  });

  describe("addLiquidity", function () {
    it("should emit Mint and LiquidityAdded events with correct parameters", async function () {
      const amountA = ethers.parseEther("1000");
      const amountB = ethers.parseEther("2000");

      const tx = await ammPool.addLiquidity(amountA, amountB);
      const receipt = await tx.wait();

      // Check Mint event via contract emit
      await expect(tx)
        .to.emit(ammPool, "Mint")
        .withArgs(owner.address, amountA, amountB);

      // Check LiquidityAdded event via contract emit
      const lpTokens = await ammPool.liquidity(owner.address);
      await expect(tx)
        .to.emit(ammPool, "LiquidityAdded")
        .withArgs(owner.address, amountA, amountB, lpTokens);
    });
  });

  describe("swap", function () {
    beforeEach(async function () {
      // Add initial liquidity
      const amountA = ethers.parseEther("1000");
      const amountB = ethers.parseEther("2000");
      await ammPool.addLiquidity(amountA, amountB);
    });

    it("should emit Swap and Sync events with correct parameters and indexing", async function () {
      const amountIn = ethers.parseEther("10");
      const minAmountOut = 0; // slippage protection disabled for test
      
      const tokenAAddress = await tokenA.getAddress();
      const tx = await ammPool.swap(tokenAAddress, amountIn, minAmountOut);
      const receipt = await tx.wait();

      // Check Sync event
      const reserveA = await ammPool.reserveA();
      const reserveB = await ammPool.reserveB();
      await expect(tx)
        .to.emit(ammPool, "Sync")
        .withArgs(reserveA, reserveB);

      // Check Swap event
      const amountOut = await tokenB.balanceOf(owner.address) - ethers.parseEther("998000"); // 1M minus initial deposit
      await expect(tx)
        .to.emit(ammPool, "Swap");

      // Verify that event parameters are indexed correctly
      const swapLog = receipt.logs.find(log => log.fragment && log.fragment.name === "Swap");
      expect(swapLog).to.not.be.undefined;
      
      // index 0 -> user (address indexed)
      // index 1 -> tokenIn (address indexed)
      expect(swapLog.fragment.inputs[0].indexed).to.be.true;
      expect(swapLog.fragment.inputs[1].indexed).to.be.true;
    });
  });

  describe("removeLiquidity", function () {
    const amountA = ethers.parseEther("1000");
    const amountB = ethers.parseEther("2000");

    beforeEach(async function () {
      await ammPool.addLiquidity(amountA, amountB);
    });

    it("should emit Burn and LiquidityRemoved events with correct parameters", async function () {
      const lpTokens = await ammPool.liquidity(owner.address);

      const tx = await ammPool.removeLiquidity(lpTokens);
      
      // Check Burn event
      await expect(tx)
        .to.emit(ammPool, "Burn")
        .withArgs(owner.address, amountA, amountB, owner.address);

      // Check LiquidityRemoved event
      await expect(tx)
        .to.emit(ammPool, "LiquidityRemoved")
        .withArgs(owner.address, amountA, amountB);
    });
  });
});
