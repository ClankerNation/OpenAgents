const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AMMPool", function () {
  let pool, tokenA, tokenB, owner, user1, user2;

  beforeEach(async function () {
    [owner, user1, user2] = await ethers.getSigners();

    const ERC20Mock = await ethers.getContractFactory("ERC20Mock");
    tokenA = await ERC20Mock.deploy("Token A", "TKA", 18);
    tokenB = await ERC20Mock.deploy("Token B", "TKB", 18);

    const AMMPool = await ethers.getContractFactory("AMMPool");
    pool = await AMMPool.deploy(tokenA.target, tokenB.target);

    await tokenA.mint(user1.address, ethers.parseEther("10000"));
    await tokenB.mint(user1.address, ethers.parseEther("10000"));
    await tokenA.mint(user2.address, ethers.parseEther("10000"));
    await tokenB.mint(user2.address, ethers.parseEther("10000"));

    await tokenA.connect(user1).approve(pool.target, ethers.MaxUint256);
    await tokenB.connect(user1).approve(pool.target, ethers.MaxUint256);
    await tokenA.connect(user2).approve(pool.target, ethers.MaxUint256);
    await tokenB.connect(user2).approve(pool.target, ethers.MaxUint256);
  });

  it("Should lock MINIMUM_LIQUIDITY to address(0) on first deposit", async function () {
    await pool.connect(user1).addLiquidity(ethers.parseEther("100"), ethers.parseEther("100"));
    
    const minLiq = await pool.MINIMUM_LIQUIDITY();
    expect(await pool.liquidity(ethers.ZeroAddress)).to.equal(minLiq);
    
    const totalLiq = await pool.totalLiquidity();
    const userLiq = await pool.liquidity(user1.address);
    expect(totalLiq).to.equal(userLiq + minLiq);
  });

  it("Should prevent first-depositor inflation attack", async function () {
    // Use amounts large enough to exceed MINIMUM_LIQUIDITY (1000)
    await pool.connect(user1).addLiquidity(ethers.parseEther("1"), ethers.parseEther("1"));
    
    // Attacker donates to inflate price
    await tokenA.connect(user1).transfer(pool.target, ethers.parseEther("10"));
    
    // Victim deposits
    await pool.connect(user2).addLiquidity(ethers.parseEther("100"), ethers.parseEther("100"));
    
    const victimLiq = await pool.liquidity(user2.address);
    await pool.connect(user2).removeLiquidity(victimLiq);
    
    // Victim should get back ~100 tokens, not be drained
    const victimBalA = await tokenA.balanceOf(user2.address);
    expect(victimBalA).to.be.gte(ethers.parseEther("9999"));
    expect(victimBalA).to.be.lte(ethers.parseEther("10001"));
  });

  it("Should use internal reserves in removeLiquidity and trap donations", async function () {
    await pool.connect(user1).addLiquidity(ethers.parseEther("100"), ethers.parseEther("100"));
    
    // Attacker donates 50 tokens to the pool to inflate the price
    await tokenA.connect(user1).transfer(pool.target, ethers.parseEther("50"));
    
    const reserveA = await pool.reserveA();
    const balA = await tokenA.balanceOf(pool.target);
    expect(balA).to.be.gt(reserveA); // Pool has more tokens than internal reserves
    
    const liq = await pool.liquidity(user1.address);
    await pool.connect(user1).removeLiquidity(liq);
    
    // User should only get back their original 100 tokens (minus MINIMUM_LIQUIDITY dust)
    // They should NOT get the donated 50 tokens (the fix prevents stealing donations)
    const finalBal = await tokenA.balanceOf(user1.address);
    expect(finalBal).to.be.lte(ethers.parseEther("9951")); 
    expect(finalBal).to.be.gte(ethers.parseEther("9949"));
    
    // The donated 50 tokens should remain trapped in the contract
    const finalPoolBal = await tokenA.balanceOf(pool.target);
    expect(finalPoolBal).to.be.gte(ethers.parseEther("50"));
  });

  it("Should allow sync() to update reserves to actual balances", async function () {
    await pool.connect(user1).addLiquidity(ethers.parseEther("100"), ethers.parseEther("100"));
    await tokenA.connect(user1).transfer(pool.target, ethers.parseEther("50"));
    
    let reserveA = await pool.reserveA();
    expect(reserveA).to.equal(ethers.parseEther("100"));
    
    await pool.sync();
    
    reserveA = await pool.reserveA();
    expect(reserveA).to.equal(ethers.parseEther("150"));
  });
});
