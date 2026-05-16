const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("InterestRateModel", function () {
  let interestRateModel;
  let admin, other;

  const BASE_RATE = ethers.utils.parseEther("0.02");       // 2%
  const MULTIPLIER = ethers.utils.parseEther("0.1");       // 10%
  const JUMP_MULTIPLIER = ethers.utils.parseEther("1.0");  // 100%
  const KINK = ethers.utils.parseEther("0.8");             // 80%

  beforeEach(async function () {
    [admin, other] = await ethers.getSigners();

    const InterestRateModel = await ethers.getContractFactory("InterestRateModel");
    interestRateModel = await InterestRateModel.deploy(
      BASE_RATE,
      MULTIPLIER,
      JUMP_MULTIPLIER,
      KINK
    );
    await interestRateModel.deployed();
  });

  describe("Constructor", function () {
    it("should set initial parameters correctly", async function () {
      expect(await interestRateModel.baseRate()).to.equal(BASE_RATE);
      expect(await interestRateModel.multiplier()).to.equal(MULTIPLIER);
      expect(await interestRateModel.jumpMultiplier()).to.equal(JUMP_MULTIPLIER);
      expect(await interestRateModel.kink()).to.equal(KINK);
    });

    it("should set deployer as admin", async function () {
      expect(await interestRateModel.admin()).to.equal(admin.address);
    });
  });

  describe("getParameters", function () {
    it("should return all parameters in a struct", async function () {
      const params = await interestRateModel.getParameters();
      expect(params.baseRate).to.equal(BASE_RATE);
      expect(params.multiplier).to.equal(MULTIPLIER);
      expect(params.jumpMultiplier).to.equal(JUMP_MULTIPLIER);
      expect(params.kink).to.equal(KINK);
    });

    it("should reflect updated parameters", async function () {
      const newBase = ethers.utils.parseEther("0.03");
      const newMult = ethers.utils.parseEther("0.15");
      const newJump = ethers.utils.parseEther("1.2");
      const newKink = ethers.utils.parseEther("0.85");

      await interestRateModel.updateParams(newBase, newMult, newJump, newKink);

      const params = await interestRateModel.getParameters();
      expect(params.baseRate).to.equal(newBase);
      expect(params.multiplier).to.equal(newMult);
      expect(params.jumpMultiplier).to.equal(newJump);
      expect(params.kink).to.equal(newKink);
    });
  });

  describe("RateParametersUpdated event", function () {
    it("should emit event with old and new values on updateParams", async function () {
      const newBase = ethers.utils.parseEther("0.05");
      const newMult = ethers.utils.parseEther("0.2");
      const newJump = ethers.utils.parseEther("1.5");
      const newKink = ethers.utils.parseEther("0.9");

      await expect(
        interestRateModel.updateParams(newBase, newMult, newJump, newKink)
      )
        .to.emit(interestRateModel, "RateParametersUpdated")
        .withArgs(
          BASE_RATE, newBase,           // oldBaseRate, newBaseRate
          MULTIPLIER, newMult,          // oldMultiplier, newMultiplier
          JUMP_MULTIPLIER, newJump,     // oldJumpMultiplier, newJumpMultiplier
          KINK, newKink                 // oldKink, newKink
        );
    });

    it("should emit event when updating to same values", async function () {
      // Even same-value updates should emit (for audit trail)
      await expect(
        interestRateModel.updateParams(BASE_RATE, MULTIPLIER, JUMP_MULTIPLIER, KINK)
      )
        .to.emit(interestRateModel, "RateParametersUpdated")
        .withArgs(
          BASE_RATE, BASE_RATE,
          MULTIPLIER, MULTIPLIER,
          JUMP_MULTIPLIER, JUMP_MULTIPLIER,
          KINK, KINK
        );
    });

    it("should allow multiple sequential updates", async function () {
      const first = {
        base: ethers.utils.parseEther("0.03"),
        mult: ethers.utils.parseEther("0.12"),
        jump: ethers.utils.parseEther("1.1"),
        kink: ethers.utils.parseEther("0.82"),
      };
      const second = {
        base: ethers.utils.parseEther("0.04"),
        mult: ethers.utils.parseEther("0.18"),
        jump: ethers.utils.parseEther("2.0"),
        kink: ethers.utils.parseEther("0.75"),
      };

      await interestRateModel.updateParams(first.base, first.mult, first.jump, first.kink);

      await expect(
        interestRateModel.updateParams(second.base, second.mult, second.jump, second.kink)
      )
        .to.emit(interestRateModel, "RateParametersUpdated")
        .withArgs(
          first.base, second.base,
          first.mult, second.mult,
          first.jump, second.jump,
          first.kink, second.kink
        );
    });
  });

  describe("Access Control", function () {
    it("should reject updateParams from non-admin", async function () {
      await expect(
        interestRateModel.connect(other).updateParams(
          ethers.utils.parseEther("0.99"),
          MULTIPLIER,
          JUMP_MULTIPLIER,
          KINK
        )
      ).to.be.revertedWith("Not admin");
    });

    it("should allow admin to update", async function () {
      const newBase = ethers.utils.parseEther("0.07");
      await interestRateModel.updateParams(newBase, MULTIPLIER, JUMP_MULTIPLIER, KINK);
      expect(await interestRateModel.baseRate()).to.equal(newBase);
    });
  });

  describe("getUtilization", function () {
    it("should return 0 when deposits are zero", async function () {
      expect(await interestRateModel.getUtilization(100, 0)).to.equal(0);
    });

    it("should compute utilization correctly", async function () {
      const borrowed = ethers.utils.parseEther("500");
      const deposits = ethers.utils.parseEther("1000");
      const expectedUtil = ethers.utils.parseEther("0.5"); // 50%
      expect(await interestRateModel.getUtilization(borrowed, deposits)).to.equal(expectedUtil);
    });
  });

  describe("getBorrowRate", function () {
    it("should return base rate at zero utilization", async function () {
      const rate = await interestRateModel.getBorrowRate(0, ethers.utils.parseEther("1000"));
      expect(rate).to.equal(BASE_RATE);
    });

    it("should increase rate with utilization below kink", async function () {
      const borrowed = ethers.utils.parseEther("400");
      const deposits = ethers.utils.parseEther("1000");
      const rate = await interestRateModel.getBorrowRate(borrowed, deposits);
      expect(rate).to.be.gt(BASE_RATE);
    });

    it("should apply jump multiplier above kink", async function () {
      const borrowed = ethers.utils.parseEther("900");
      const deposits = ethers.utils.parseEther("1000");
      const rate = await interestRateModel.getBorrowRate(borrowed, deposits);
      // Rate should be significantly higher due to jump multiplier
      expect(rate).to.be.gt(ethers.utils.parseEther("0.1")); // > 10%
    });
  });
});
