const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("InterestRateModel", function () {
  let rateModel;
  let admin, nonAdmin;

  const INITIAL_BASE_RATE = ethers.parseUnits("0.02", 18);     // 2%
  const INITIAL_MULTIPLIER = ethers.parseUnits("0.1", 18);      // 10%
  const INITIAL_JUMP = ethers.parseUnits("1.0", 18);            // 100%
  const INITIAL_KINK = ethers.parseUnits("0.8", 18);            // 80%

  beforeEach(async function () {
    [admin, nonAdmin] = await ethers.getSigners();
    const RateModel = await ethers.getContractFactory("InterestRateModel");
    rateModel = await RateModel.deploy(
      INITIAL_BASE_RATE,
      INITIAL_MULTIPLIER,
      INITIAL_JUMP,
      INITIAL_KINK
    );
    await rateModel.waitForDeployment();
  });

  describe("Constructor", function () {
    it("should set initial parameters correctly", async function () {
      expect(await rateModel.baseRate()).to.equal(INITIAL_BASE_RATE);
      expect(await rateModel.multiplier()).to.equal(INITIAL_MULTIPLIER);
      expect(await rateModel.jumpMultiplier()).to.equal(INITIAL_JUMP);
      expect(await rateModel.kink()).to.equal(INITIAL_KINK);
      expect(await rateModel.admin()).to.equal(admin.address);
    });
  });

  describe("getParameters", function () {
    it("should return all parameters in a struct", async function () {
      const params = await rateModel.getParameters();
      expect(params.baseRate).to.equal(INITIAL_BASE_RATE);
      expect(params.multiplier).to.equal(INITIAL_MULTIPLIER);
      expect(params.jumpMultiplier).to.equal(INITIAL_JUMP);
      expect(params.kink).to.equal(INITIAL_KINK);
    });

    it("should reflect parameter changes", async function () {
      const newBase = ethers.parseUnits("0.05", 18);
      const newMult = ethers.parseUnits("0.2", 18);
      const newJump = ethers.parseUnits("2.0", 18);
      const newKink = ethers.parseUnits("0.9", 18);

      await rateModel.connect(admin).updateParams(newBase, newMult, newJump, newKink);

      const params = await rateModel.getParameters();
      expect(params.baseRate).to.equal(newBase);
      expect(params.multiplier).to.equal(newMult);
      expect(params.jumpMultiplier).to.equal(newJump);
      expect(params.kink).to.equal(newKink);
    });
  });

  describe("updateParams", function () {
    it("should emit RateParametersUpdated with old and new values", async function () {
      const newBase = ethers.parseUnits("0.05", 18);
      const newMult = ethers.parseUnits("0.2", 18);
      const newJump = ethers.parseUnits("2.0", 18);
      const newKink = ethers.parseUnits("0.9", 18);

      await expect(
        rateModel.connect(admin).updateParams(newBase, newMult, newJump, newKink)
      )
        .to.emit(rateModel, "RateParametersUpdated")
        .withArgs(
          INITIAL_BASE_RATE, newBase,
          INITIAL_MULTIPLIER, newMult,
          INITIAL_JUMP, newJump,
          INITIAL_KINK, newKink
        );
    });

    it("should update all state variables", async function () {
      const newBase = ethers.parseUnits("0.05", 18);
      const newMult = ethers.parseUnits("0.2", 18);
      const newJump = ethers.parseUnits("2.0", 18);
      const newKink = ethers.parseUnits("0.9", 18);

      await rateModel.connect(admin).updateParams(newBase, newMult, newJump, newKink);

      expect(await rateModel.baseRate()).to.equal(newBase);
      expect(await rateModel.multiplier()).to.equal(newMult);
      expect(await rateModel.jumpMultiplier()).to.equal(newJump);
      expect(await rateModel.kink()).to.equal(newKink);
    });

    it("should revert when called by non-admin", async function () {
      await expect(
        rateModel.connect(nonAdmin).updateParams(0, 0, 0, 0)
      ).to.be.revertedWith("Not admin");
    });
  });

  describe("Individual setters", function () {
    describe("setBaseRate", function () {
      it("should update baseRate and emit event with old value", async function () {
        const newValue = ethers.parseUnits("0.07", 18);

        await expect(rateModel.connect(admin).setBaseRate(newValue))
          .to.emit(rateModel, "RateParametersUpdated")
          .withArgs(
            INITIAL_BASE_RATE, newValue,
            INITIAL_MULTIPLIER, INITIAL_MULTIPLIER,
            INITIAL_JUMP, INITIAL_JUMP,
            INITIAL_KINK, INITIAL_KINK
          );

        expect(await rateModel.baseRate()).to.equal(newValue);
        // Other params unchanged
        expect(await rateModel.multiplier()).to.equal(INITIAL_MULTIPLIER);
      });

      it("should revert when called by non-admin", async function () {
        await expect(
          rateModel.connect(nonAdmin).setBaseRate(0)
        ).to.be.revertedWith("Not admin");
      });
    });

    describe("setMultiplier", function () {
      it("should update multiplier and emit event with old value", async function () {
        const newValue = ethers.parseUnits("0.15", 18);

        await expect(rateModel.connect(admin).setMultiplier(newValue))
          .to.emit(rateModel, "RateParametersUpdated")
          .withArgs(
            INITIAL_BASE_RATE, INITIAL_BASE_RATE,
            INITIAL_MULTIPLIER, newValue,
            INITIAL_JUMP, INITIAL_JUMP,
            INITIAL_KINK, INITIAL_KINK
          );

        expect(await rateModel.multiplier()).to.equal(newValue);
        expect(await rateModel.baseRate()).to.equal(INITIAL_BASE_RATE);
      });

      it("should revert when called by non-admin", async function () {
        await expect(
          rateModel.connect(nonAdmin).setMultiplier(0)
        ).to.be.revertedWith("Not admin");
      });
    });

    describe("setJumpMultiplier", function () {
      it("should update jumpMultiplier and emit event with old value", async function () {
        const newValue = ethers.parseUnits("1.5", 18);

        await expect(rateModel.connect(admin).setJumpMultiplier(newValue))
          .to.emit(rateModel, "RateParametersUpdated")
          .withArgs(
            INITIAL_BASE_RATE, INITIAL_BASE_RATE,
            INITIAL_MULTIPLIER, INITIAL_MULTIPLIER,
            INITIAL_JUMP, newValue,
            INITIAL_KINK, INITIAL_KINK
          );

        expect(await rateModel.jumpMultiplier()).to.equal(newValue);
      });

      it("should revert when called by non-admin", async function () {
        await expect(
          rateModel.connect(nonAdmin).setJumpMultiplier(0)
        ).to.be.revertedWith("Not admin");
      });
    });

    describe("setKink", function () {
      it("should update kink and emit event with old value", async function () {
        const newValue = ethers.parseUnits("0.85", 18);

        await expect(rateModel.connect(admin).setKink(newValue))
          .to.emit(rateModel, "RateParametersUpdated")
          .withArgs(
            INITIAL_BASE_RATE, INITIAL_BASE_RATE,
            INITIAL_MULTIPLIER, INITIAL_MULTIPLIER,
            INITIAL_JUMP, INITIAL_JUMP,
            INITIAL_KINK, newValue
          );

        expect(await rateModel.kink()).to.equal(newValue);
      });

      it("should revert when called by non-admin", async function () {
        await expect(
          rateModel.connect(nonAdmin).setKink(0)
        ).to.be.revertedWith("Not admin");
      });
    });
  });

  describe("getBorrowRate (existing functionality preserved)", function () {
    it("should return base rate at zero utilization", async function () {
      const rate = await rateModel.getBorrowRate(0, ethers.parseUnits("1000", 18));
      expect(rate).to.equal(INITIAL_BASE_RATE);
    });

    it("should increase rate below kink", async function () {
      const borrowed = ethers.parseUnits("400", 18);
      const deposited = ethers.parseUnits("1000", 18);
      const rate = await rateModel.getBorrowRate(borrowed, deposited);
      // 40% util: 0.02 + (0.4 * 0.1) = 0.06
      expect(rate).to.equal(ethers.parseUnits("0.06", 18));
    });
  });
});
