const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("InterestRateModel", function () {
  let model;
  const PRECISION = 1n * 10n ** 18n;
  const MAX_UTILIZATION = (PRECISION * 9999n) / 10000n;

  // Default params: 10% base, 15% multiplier, 100% jumpMultiplier, 80% kink
  const BASE_RATE   = 1n * 10n ** 17n;  // 0.1e18 = 10%
  const MULTIPLIER  = 15n * 10n ** 16n; // 0.15e18 = 15%
  const JUMP_MULT   = 1n * 10n ** 18n;  // 1e18 = 100%
  const KINK        = 8n * 10n ** 17n;  // 0.8e18 = 80%

  beforeEach(async function () {
    const Factory = await ethers.getContractFactory("InterestRateModel");
    model = await Factory.deploy(BASE_RATE, MULTIPLIER, JUMP_MULT, KINK);
  });

  describe("Deployment validation", function () {
    it("should deploy with valid base rate", async function () {
      expect(await model.baseRate()).to.equal(BASE_RATE);
      expect(await model.kink()).to.equal(KINK);
    });

    it("should reject base rate below 0.1%", async function () {
      const Factory = await ethers.getContractFactory("InterestRateModel");
      await expect(
        Factory.deploy(1n * 10n ** 14n, MULTIPLIER, JUMP_MULT, KINK) // 0.01%
      ).to.be.revertedWith("Base rate out of bounds [0.1%-50%]");
    });

    it("should reject base rate above 50%", async function () {
      const Factory = await ethers.getContractFactory("InterestRateModel");
      await expect(
        Factory.deploy(6n * 10n ** 17n, MULTIPLIER, JUMP_MULT, KINK) // 60%
      ).to.be.revertedWith("Base rate out of bounds [0.1%-50%]");
    });

    it("should reject kink above MAX_UTILIZATION", async function () {
      const Factory = await ethers.getContractFactory("InterestRateModel");
      await expect(
        Factory.deploy(BASE_RATE, MULTIPLIER, JUMP_MULT, PRECISION) // 100% kink
      ).to.be.revertedWith("Kink exceeds max utilization");
    });
  });

  describe("getUtilization", function () {
    it("returns 0 when deposits are 0", async function () {
      expect(await model.getUtilization(100, 0)).to.equal(0);
    });

    it("returns correct utilization at 0%", async function () {
      const u = await model.getUtilization(0, 100n * PRECISION);
      expect(u).to.equal(0);
    });

    it("returns correct utilization at 50%", async function () {
      const u = await model.getUtilization(50n * PRECISION, 100n * PRECISION);
      expect(u).to.equal(5n * 10n ** 17n);
    });

    it("returns correct utilization at 99%", async function () {
      const u = await model.getUtilization(99n * PRECISION, 100n * PRECISION);
      expect(u).to.equal(99n * 10n ** 16n);
    });

    it("caps utilization at 99.99% when at 100%", async function () {
      const u = await model.getUtilization(100n * PRECISION, 100n * PRECISION);
      expect(u).to.equal(MAX_UTILIZATION);
    });

    it("caps utilization at 99.99% when over 100%", async function () {
      const u = await model.getUtilization(200n * PRECISION, 100n * PRECISION);
      expect(u).to.equal(MAX_UTILIZATION);
    });
  });

  describe("getBorrowRate", function () {
    it("returns base rate at 0% utilization", async function () {
      const rate = await model.getBorrowRate(0, 100n * PRECISION);
      expect(rate).to.equal(BASE_RATE);
    });

    it("returns correct rate at 50% utilization (below kink)", async function () {
      const rate = await model.getBorrowRate(50n * PRECISION, 100n * PRECISION);
      const expected = BASE_RATE + (5n * 10n ** 17n * MULTIPLIER) / PRECISION;
      expect(rate).to.equal(expected);
    });

    it("returns correct rate at 80% utilization (at kink boundary)", async function () {
      const rate = await model.getBorrowRate(80n * PRECISION, 100n * PRECISION);
      // kink == utilization, so it uses the <= kink branch
      const expected = BASE_RATE + (KINK * MULTIPLIER) / PRECISION;
      expect(rate).to.equal(expected);
    });

    it("includes jump rate at 99% utilization (above kink)", async function () {
      const rate = await model.getBorrowRate(99n * PRECISION, 100n * PRECISION);
      const normalRate = BASE_RATE + (KINK * MULTIPLIER) / PRECISION;
      const excessUtil = 99n * 10n ** 16n - KINK; // 0.99e18 - 0.8e18
      const expectedJump = (excessUtil * JUMP_MULT) / (PRECISION - KINK);
      expect(rate).to.equal(normalRate + expectedJump);
    });

    it("never reverts at 100% utilization (division by zero prevented)", async function () {
      const rate = await model.getBorrowRate(100n * PRECISION, 100n * PRECISION);
      // Should not revert; returns a bounded rate
      expect(rate).to.be.a("bigint");
      expect(rate).to.be.above(0n);
    });

    it("rate is bounded (never exceeds reasonable max)", async function () {
      const rate = await model.getBorrowRate(100n * PRECISION, 100n * PRECISION);
      // Even at max utilization + jump, rate should be bounded
      const maxReasonableRate = (BASE_RATE + JUMP_MULT) * 2n;
      expect(rate).to.be.below(maxReasonableRate);
    });
  });

  describe("getSupplyRate", function () {
    it("returns 0 when nothing is borrowed", async function () {
      const rate = await model.getSupplyRate(0, 100n * PRECISION, 0);
      expect(rate).to.equal(0);
    });

    it("respects reserve factor", async function () {
      const reserveFactor = 1n * 10n ** 17n; // 10%
      const rateNoReserve = await model.getSupplyRate(50n * PRECISION, 100n * PRECISION, 0);
      const rateWithReserve = await model.getSupplyRate(50n * PRECISION, 100n * PRECISION, reserveFactor);
      expect(rateWithReserve).to.be.below(rateNoReserve);
    });
  });

  describe("updateParams", function () {
    it("should update base rate within bounds", async function () {
      await model.updateParams(2n * 10n ** 17n, MULTIPLIER, JUMP_MULT, KINK);
      expect(await model.baseRate()).to.equal(2n * 10n ** 17n);
    });

    it("should reject out-of-bounds base rate", async function () {
      await expect(
        model.updateParams(6n * 10n ** 17n, MULTIPLIER, JUMP_MULT, KINK)
      ).to.be.revertedWith("Base rate out of bounds [0.1%-50%]");
    });

    it("should reject kink exceeding max utilization", async function () {
      await expect(
        model.updateParams(BASE_RATE, MULTIPLIER, JUMP_MULT, PRECISION)
      ).to.be.revertedWith("Kink exceeds max utilization");
    });

    it("should emit event on update", async function () {
      await expect(
        model.updateParams(2n * 10n ** 17n, MULTIPLIER, JUMP_MULT, KINK)
      ).to.emit(model, "RateParamsUpdated");
    });
  });
});
