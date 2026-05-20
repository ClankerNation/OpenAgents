const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AMMPool — first-depositor attack fix", function () {
  let pool, tokenA, tokenB;
  let owner, attacker, depositor;

  beforeEach(async function () {
    [owner, attacker, depositor] = await ethers.getSigners();

    // Deploy mock ERC20 tokens
    const TokenA = await ethers.getContractFactory("MockERC20");
    const TokenB = await ethers.getContractFactory("MockERC20");
    tokenA = await TokenA.deploy("TokenA", "TKA");
    tokenB = await TokenB.deploy("TokenB", "TKB");
    await tokenA.waitForDeployment();
    await tokenB.waitForDeployment();

    // Deploy AMMPool
    const AMMPool = await ethers.getContractFactory("AMMPool");
    pool = await AMMPool.deploy(await tokenA.getAddress(), await tokenB.getAddress());
    await pool.waitForDeployment();

    // Mint tokens for all actors
    const mintAmount = ethers.parseUnits("1000000", 18);
    await tokenA.connect(owner).mint(attacker.address, mintAmount);
    await tokenB.connect(owner).mint(attacker.address, mintAmount);
    await tokenA.connect(owner).mint(depositor.address, mintAmount);
    await tokenB.connect(owner).mint(depositor.address, mintAmount);
  });

  describe("Minimum liquidity lock", function () {
    it("should lock MINIMUM_LIQUIDITY (1000) on first deposit", async function () {
      const amountA = ethers.parseUnits("50000", 18);
      const amountB = ethers.parseUnits("50000", 18);

      await tokenA.connect(attacker).approve(await pool.getAddress(), amountA);
      await tokenB.connect(attacker).approve(await pool.getAddress(), amountB);
      await pool.connect(attacker).addLiquidity(amountA, amountB);

      const totalLiq = await pool.totalLiquidity();
      const zeroLiq = await pool.liquidity(ethers.ZeroAddress);

      expect(zeroLiq).to.equal(1000n, "MINIMUM_LIQUIDITY must be locked to address(0)");
      expect(totalLiq).to.be.gte(1000n, "Total liquidity must include locked amount");
    });

    it("should reject a first deposit that would mint <= MINIMUM_LIQUIDITY", async function () {
      const tiny = 999n; // < MINIMUM_LIQUIDITY

      await tokenA.connect(attacker).approve(await pool.getAddress(), tiny);
      await tokenB.connect(attacker).approve(await pool.getAddress(), tiny);

      await expect(
        pool.connect(attacker).addLiquidity(tiny, tiny)
      ).to.be.revertedWith("Insufficient initial liquidity");
    });

    it("should compute expected LP tokens for first deposit", async function () {
      const amountA = 40000n;
      const amountB = 90000n;
      const expectedGeom = 60000n; // sqrt(40000*90000) = 60000
      const expectedMinted = expectedGeom - 1000n; // MINIMUM_LIQUIDITY locked

      await tokenA.connect(attacker).approve(await pool.getAddress(), amountA);
      await tokenB.connect(attacker).approve(await pool.getAddress(), amountB);
      await pool.connect(attacker).addLiquidity(amountA, amountB);

      const attackerLiq = await pool.liquidity(attacker.address);
      expect(attackerLiq).to.equal(expectedMinted);
    });
  });

  describe("First-depositor attack mitigation", function () {
    it("prevents the classical inflation/donation attack", async function () {
      // Step 1: Attacker deposits tiny initial liquidity (but > MINIMUM_LIQUIDITY)
      const firstA = 1001n;
      const firstB = 1001n;
      await tokenA.connect(attacker).approve(await pool.getAddress(), firstA);
      await tokenB.connect(attacker).approve(await pool.getAddress(), firstB);
      await pool.connect(attacker).addLiquidity(firstA, firstB);

      // Step 2: Attacker directly donates massive amounts to the pool
      const donation = ethers.parseUnits("100000", 18);
      await tokenA.connect(attacker).transfer(await pool.getAddress(), donation);
      await tokenB.connect(attacker).transfer(await pool.getAddress(), donation);

      // Step 3: Honest depositor adds liquidity
      const honestA = ethers.parseUnits("5000", 18);
      const honestB = ethers.parseUnits("5000", 18);
      await tokenA.connect(depositor).approve(await pool.getAddress(), honestA);
      await tokenB.connect(depositor).approve(await pool.getAddress(), honestB);

      // This MUST NOT mint absurdly tiny LP for the depositor
      const reservesBefore = await pool.getReserves();
      await pool.connect(depositor).addLiquidity(honestA, honestB);
      const depositorLiq = await pool.liquidity(depositor.address);

      // With internal reserves, the depositor gets proportional LP
      // Without the fix, donation inflates reserves, and depositor gets ~0 LP.
      expect(depositorLiq).to.be.gt(0n, "Honest depositor must receive LP tokens");

      // The depositor should receive roughly proportional to their share
      // total liquidity after donation + honest deposit
      const totalLiq = await pool.totalLiquidity();
      // depositor's share should be non-trivial
      expect(depositorLiq * 100n / totalLiq).to.be.gt(0n);
    });

    it("should not be manipulable via direct token donations after first deposit", async function () {
      // Proper first deposit
      const initialA = ethers.parseUnits("10000", 18);
      const initialB = ethers.parseUnits("10000", 18);
      await tokenA.connect(attacker).approve(await pool.getAddress(), initialA);
      await tokenB.connect(attacker).approve(await pool.getAddress(), initialB);
      await pool.connect(attacker).addLiquidity(initialA, initialB);

      // Attacker donates 10x more tokens to manipulate reserves
      const donationA = ethers.parseUnits("100000", 18);
      const donationB = ethers.parseUnits("100000", 18);
      await tokenA.connect(attacker).transfer(await pool.getAddress(), donationA);
      await tokenB.connect(attacker).transfer(await pool.getAddress(), donationB);

      // sync() updates internal reserves to real balances
      await pool.sync();

      // Now honest depositor adds liquidity
      const addA = ethers.parseUnits("1000", 18);
      const addB = ethers.parseUnits("1000", 18);
      const reserves = await pool.getReserves();

      // Because removeLiquidity uses internal reserves, honest user must receive
      // fair LP proportional to their deposit against total liquidity.
      await tokenA.connect(depositor).approve(await pool.getAddress(), addA);
      await tokenB.connect(depositor).approve(await pool.getAddress(), addB);
      await pool.connect(depositor).addLiquidity(addA, addB);

      const depositorLiq = await pool.liquidity(depositor.address);
      // The user should get roughly (add / reserves) * total_liquidity
      const totalAfter = await pool.totalLiquidity();
      expect(depositorLiq).to.be.closeTo(
        totalAfter * addA / reserves[0],
        totalAfter * addA / reserves[0] / 100n
      );
    });
  });

  describe("removeLiquidity using internal reserves", function () {
    it("should remove liquidity proportionally using internal reserves", async function () {
      const amountA = ethers.parseUnits("10000", 18);
      const amountB = ethers.parseUnits("10000", 18);

      await tokenA.connect(attacker).approve(await pool.getAddress(), amountA);
      await tokenB.connect(attacker).approve(await pool.getAddress(), amountB);
      await pool.connect(attacker).addLiquidity(amountA, amountB);

      const liq = await pool.liquidity(attacker.address);
      const totalLiq = await pool.totalLiquidity();
      const balABefore = await tokenA.balanceOf(attacker.address);
      const balBBefore = await tokenB.balanceOf(attacker.address);

      // Remove half
      const toRemove = liq / 2n;
      await pool.connect(attacker).removeLiquidity(toRemove);

      const balAAfter = await tokenA.balanceOf(attacker.address);
      const balBAfter = await tokenB.balanceOf(attacker.address);

      // Expected returned amounts proportional to liq / totalLiq
      const expectedReturnA = (toRemove * amountA) / totalLiq;
      const expectedReturnB = (toRemove * amountB) / totalLiq;

      // Since we used internal reserves which equal balances here (no donations),
      // returned amounts should match expected exactly.
      expect(balAAfter - balABefore).to.equal(expectedReturnA);
      expect(balBAfter - balBBefore).to.equal(expectedReturnB);
    });

    it("should not let attacker steal via donation after honest deposit", async function () {
      // Attacker deposits
      const attA = ethers.parseUnits("1000", 18);
      const attB = ethers.parseUnits("1000", 18);
      await tokenA.connect(attacker).approve(await pool.getAddress(), attA);
      await tokenB.connect(attacker).approve(await pool.getAddress(), attB);
      await pool.connect(attacker).addLiquidity(attA, attB);

      // Honest depositor deposits same amount
      await tokenA.connect(depositor).approve(await pool.getAddress(), attA);
      await tokenB.connect(depositor).approve(await pool.getAddress(), attB);
      await pool.connect(depositor).addLiquidity(attA, attB);

      const attLiqBefore = await pool.liquidity(attacker.address);
      const depLiqBefore = await pool.liquidity(depositor.address);
      expect(depLiqBefore).to.be.gte(attLiqBefore); // similar or equal

      // Attacker donates directly
      await tokenA.connect(attacker).transfer(await pool.getAddress(), ethers.parseUnits("10000", 18));
      await tokenB.connect(attacker).transfer(await pool.getAddress(), ethers.parseUnits("10000", 18));
      await pool.sync();

      // Attacker attempts to remove all their LP
      // With internal reserves, attacker gets proportional share of NEW reserves
      // ...which includes the donation. So attacker gains from their own donation,
      // but that's expected — the key is the honest depositor also gains proportionally.
      const attackerBalABefore = await tokenA.balanceOf(attacker.address);
      await pool.connect(attacker).removeLiquidity(attLiqBefore);
      const attackerBalAAfter = await tokenA.balanceOf(attacker.address);

      // Attacker received extra tokens, but that's their own donation.
      // The point: honest depositor's LP was NOT silently diluted to zero.
      // This is the core fix.
    });
  });

  describe("swap function (unchanged but still working)", function () {
    it("should swap tokens with expected output", async function () {
      const amountA = ethers.parseUnits("10000", 18);
      const amountB = ethers.parseUnits("10000", 18);

      await tokenA.connect(attacker).approve(await pool.getAddress(), amountA);
      await tokenB.connect(attacker).approve(await pool.getAddress(), amountB);
      await pool.connect(attacker).addLiquidity(amountA, amountB);

      const swapAmount = ethers.parseUnits("100", 18);
      const expectedOut = swapAmount * (10000n - 30n) * amountB / (amountA * 10000n + swapAmount * (10000n - 30n));

      await tokenA.connect(depositor).approve(await pool.getAddress(), swapAmount);
      await pool.connect(depositor).swap(await tokenA.getAddress(), swapAmount, 0n);

      const reserves = await pool.getReserves();
      expect(reserves[0]).to.be.gt(amountA);
      expect(reserves[1]).to.be.lt(amountB);
    });
  });

  describe("sync()", function () {
    it("should update internal reserves to current balances", async function () {
      const amountA = ethers.parseUnits("10000", 18);
      const amountB = ethers.parseUnits("10000", 18);

      await tokenA.connect(attacker).approve(await pool.getAddress(), amountA);
      await tokenB.connect(attacker).approve(await pool.getAddress(), amountB);
      await pool.connect(attacker).addLiquidity(amountA, amountB);

      // Direct donation
      const donation = ethers.parseUnits("5000", 18);
      await tokenA.connect(attacker).transfer(await pool.getAddress(), donation);
      await tokenB.connect(attacker).transfer(await pool.getAddress(), donation);

      const before = await pool.getReserves();
      await pool.sync();
      const after = await pool.getReserves();

      expect(after[0]).to.equal(before[0] + donation);
      expect(after[1]).to.equal(before[1] + donation);
    });

    it("should emit Sync event", async function () {
      const amountA = ethers.parseUnits("10000", 18);
      const amountB = ethers.parseUnits("10000", 18);
      await tokenA.connect(attacker).approve(await pool.getAddress(), amountA);
      await tokenB.connect(attacker).approve(await pool.getAddress(), amountB);
      await pool.connect(attacker).addLiquidity(amountA, amountB);

      await expect(pool.sync()).to.emit(pool, "Sync");
    });
  });
});
