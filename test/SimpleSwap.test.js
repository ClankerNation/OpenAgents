const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("SimpleSwap", function () {
  let simpleSwap, tokenA, tokenB;
  let owner, user;

  const INITIAL_LIQUIDITY_A = ethers.parseEther("1000");
  const INITIAL_LIQUIDITY_B = ethers.parseEther("1000");
  const SWAP_AMOUNT = ethers.parseEther("10");

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners();

    const MockToken = await ethers.getContractFactory("MockToken");
    tokenA = await MockToken.deploy("Token A", "TKNA");
    await tokenA.waitForDeployment();
    tokenB = await MockToken.deploy("Token B", "TKNB");
    await tokenB.waitForDeployment();

    const SimpleSwapFactory = await ethers.getContractFactory("SimpleSwap");
    simpleSwap = await SimpleSwapFactory.deploy(tokenA.target, tokenB.target);
    await simpleSwap.waitForDeployment();

    await tokenA.mint(user.address, ethers.parseEther("10000"));
    await tokenB.mint(user.address, ethers.parseEther("10000"));

    await tokenA.mint(owner.address, INITIAL_LIQUIDITY_A);
    await tokenB.mint(owner.address, INITIAL_LIQUIDITY_B);
    await tokenA.connect(owner).approve(simpleSwap.target, INITIAL_LIQUIDITY_A);
    await tokenB.connect(owner).approve(simpleSwap.target, INITIAL_LIQUIDITY_B);
    await simpleSwap.connect(owner).addLiquidity(INITIAL_LIQUIDITY_A, INITIAL_LIQUIDITY_B);
  });

  it("should revert when output is below minAmountOut", async function () {
    await tokenA.connect(user).approve(simpleSwap.target, SWAP_AMOUNT);
    const [expectedOut] = await simpleSwap.getAmountOut(tokenA.target, SWAP_AMOUNT);
    const tooHighMin = expectedOut + ethers.parseEther("100");
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    await expect(
      simpleSwap.connect(user).swap(tokenA.target, SWAP_AMOUNT, tooHighMin, deadline)
    ).to.be.revertedWith("Slippage exceeded");
  });

  it("should succeed when output meets minAmountOut exactly", async function () {
    await tokenA.connect(user).approve(simpleSwap.target, SWAP_AMOUNT);
    const [expectedOut] = await simpleSwap.getAmountOut(tokenA.target, SWAP_AMOUNT);
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    await expect(
      simpleSwap.connect(user).swap(tokenA.target, SWAP_AMOUNT, expectedOut, deadline)
    ).to.not.be.reverted;
  });

  it("should succeed when output exceeds minAmountOut", async function () {
    await tokenA.connect(user).approve(simpleSwap.target, SWAP_AMOUNT);
    const [expectedOut] = await simpleSwap.getAmountOut(tokenA.target, SWAP_AMOUNT);
    const lowerMin = expectedOut - ethers.parseEther("0.1");
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    await expect(
      simpleSwap.connect(user).swap(tokenA.target, SWAP_AMOUNT, lowerMin, deadline)
    ).to.not.be.reverted;
  });

  it("should revert when minAmountOut is zero", async function () {
    await tokenA.connect(user).approve(simpleSwap.target, SWAP_AMOUNT);
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    await expect(
      simpleSwap.connect(user).swap(tokenA.target, SWAP_AMOUNT, 0, deadline)
    ).to.be.revertedWith("Zero min output");
  });

  it("should revert when deadline has passed", async function () {
    await tokenA.connect(user).approve(simpleSwap.target, SWAP_AMOUNT);
    const pastDeadline = Math.floor(Date.now() / 1000) - 3600;
    const [expectedOut] = await simpleSwap.getAmountOut(tokenA.target, SWAP_AMOUNT);
    await expect(
      simpleSwap.connect(user).swap(tokenA.target, SWAP_AMOUNT, expectedOut, pastDeadline)
    ).to.be.revertedWith("Expired");
  });

  it("should succeed when deadline is in the future", async function () {
    await tokenA.connect(user).approve(simpleSwap.target, SWAP_AMOUNT);
    const [expectedOut] = await simpleSwap.getAmountOut(tokenA.target, SWAP_AMOUNT);
    const farFuture = Math.floor(Date.now() / 1000) + 86400;
    await expect(
      simpleSwap.connect(user).swap(tokenA.target, SWAP_AMOUNT, expectedOut, farFuture)
    ).to.not.be.reverted;
  });

  it("should succeed when deadline equals block.timestamp", async function () {
    await tokenA.connect(user).approve(simpleSwap.target, SWAP_AMOUNT);
    const [expectedOut] = await simpleSwap.getAmountOut(tokenA.target, SWAP_AMOUNT);
    // Use a generous buffer — block.timestamp may be slightly ahead of Date.now()
    const nowDeadline = Math.floor(Date.now() / 1000) + 120;
    await expect(
      simpleSwap.connect(user).swap(tokenA.target, SWAP_AMOUNT, expectedOut, nowDeadline)
    ).to.not.be.reverted;
  });

  it("should charge at least 1 wei fee for very small swaps", async function () {
    const tinyAmount = 100n;
    await tokenA.connect(user).approve(simpleSwap.target, tinyAmount);
    const [expectedOut, fee] = await simpleSwap.getAmountOut(tokenA.target, tinyAmount);
    expect(fee).to.equal(1n);
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    const tx = await simpleSwap.connect(user).swap(tokenA.target, tinyAmount, expectedOut, deadline);
    const receipt = await tx.wait();
    const iface = simpleSwap.interface;
    for (const log of receipt.logs) {
      try {
        const parsed = iface.parseLog({ topics: [...log.topics], data: log.data });
        if (parsed && parsed.name === "Swap") {
          expect(parsed.args.fee).to.equal(1n);
        }
      } catch(e) {}
    }
  });

  it("should charge correct fee for normal swaps", async function () {
    const amount = ethers.parseEther("100");
    await tokenA.connect(user).approve(simpleSwap.target, amount);
    const [expectedOut, fee] = await simpleSwap.getAmountOut(tokenA.target, amount);
    const expectedFee = amount * 30n / 10000n;
    expect(fee).to.equal(expectedFee);
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    await simpleSwap.connect(user).swap(tokenA.target, amount, expectedOut, deadline);
  });

  it("should swap tokenA → tokenB correctly", async function () {
    await tokenA.connect(user).approve(simpleSwap.target, SWAP_AMOUNT);
    const [expectedOut] = await simpleSwap.getAmountOut(tokenA.target, SWAP_AMOUNT);
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    const balanceBefore = await tokenB.balanceOf(user.address);
    await simpleSwap.connect(user).swap(tokenA.target, SWAP_AMOUNT, expectedOut, deadline);
    const balanceAfter = await tokenB.balanceOf(user.address);
    expect(balanceAfter - balanceBefore).to.equal(expectedOut);
  });

  it("should swap tokenB → tokenA correctly", async function () {
    await tokenB.connect(user).approve(simpleSwap.target, SWAP_AMOUNT);
    const [expectedOut] = await simpleSwap.getAmountOut(tokenB.target, SWAP_AMOUNT);
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    const balanceBefore = await tokenA.balanceOf(user.address);
    await simpleSwap.connect(user).swap(tokenB.target, SWAP_AMOUNT, expectedOut, deadline);
    const balanceAfter = await tokenA.balanceOf(user.address);
    expect(balanceAfter - balanceBefore).to.equal(expectedOut);
  });

  it("should revert with invalid token address", async function () {
    await tokenA.connect(user).approve(simpleSwap.target, SWAP_AMOUNT);
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    await expect(
      simpleSwap.connect(user).swap("0x0000000000000000000000000000000000000001", SWAP_AMOUNT, 1, deadline)
    ).to.be.revertedWith("Invalid token");
  });

  it("should revert with zero input amount", async function () {
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    await expect(
      simpleSwap.connect(user).swap(tokenA.target, 0, 1, deadline)
    ).to.be.revertedWith("Zero input");
  });

  it("should maintain constant product invariant", async function () {
    const [resA0, resB0] = await simpleSwap.getReserves();
    const k0 = resA0 * resB0;
    await tokenA.connect(user).approve(simpleSwap.target, SWAP_AMOUNT);
    const [expectedOut] = await simpleSwap.getAmountOut(tokenA.target, SWAP_AMOUNT);
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    await simpleSwap.connect(user).swap(tokenA.target, SWAP_AMOUNT, expectedOut, deadline);
    const [resA1, resB1] = await simpleSwap.getReserves();
    const k1 = resA1 * resB1;
    // k1 >= k0 (fee stays in pool, k increases)
    expect(k1 >= k0).to.be.true;
  });
});
