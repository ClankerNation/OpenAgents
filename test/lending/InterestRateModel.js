const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("InterestRateModel", function () {
  let model;
  let admin, nonAdmin;

  const BASE_RATE = ethers.parseUnits("0.02", 18);   // 2%
  const MULTIPLIER = ethers.parseUnits("0.1", 18);    // 10%
  const JUMP_MULTIPLIER = ethers.parseUnits("2", 18);  // 200%
  const KINK = ethers.parseUnits("0.8", 18);           // 80%

  beforeEach(async function () {
    [admin, nonAdmin] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("InterestRateModel");
    model = await Factory.deploy(BASE_RATE, MULTIPLIER, JUMP_MULTIPLIER, KINK);
  });

  describe("Deployment", function () {
    it("should set initial parameters correctly", async function () {
      expect(await model.baseRate()).to.equal(BASE_RATE);
      expect(await model.multiplier()).to.equal(MULTIPLIER);
      expect(await model.jumpMultiplier()).to.equal(JUMP_MULTIPLIER);
      expect(await model.kink()).to.equal(KINK);
    });

    it("should set admin as deployer", async function () {
      expect(await model.admin()).to.equal(admin.address);
    });
  });

  describe("getParameters", function () {
    it("should return all current parameters in one call", async function () {
      const params = await model.getParameters();
      expect(params[0]).to.equal(BASE_RATE);
      expect(params[1]).to.equal(MULTIPLIER);
      expect(params[2]).to.equal(JUMP_MULTIPLIER);
      expect(params[3]).to.equal(KINK);
    });

    it("should reflect updated parameters after change", async function () {
      const newBaseRate = ethers.parseUnits("0.05", 18);
      await model.connect(admin).setBaseRate(newBaseRate);
      const params = await model.getParameters();
      expect(params[0]).to.equal(newBaseRate);
      expect(params[1]).to.equal(MULTIPLIER);
      expect(params[2]).to.equal(JUMP_MULTIPLIER);
      expect(params[3]).to.equal(KINK);
    });
  });

  describe("setBaseRate", function () {
    it("should update base rate and emit event with old and new values", async function () {
      const newBaseRate = ethers.parseUnits("0.05", 18);
      await expect(model.connect(admin).setBaseRate(newBaseRate))
        .to.emit(model, "RateParametersUpdated")
        .withArgs(
          BASE_RATE, newBaseRate,
          MULTIPLIER, MULTIPLIER,
          JUMP_MULTIPLIER, JUMP_MULTIPLIER,
          KINK, KINK
        );
      expect(await model.baseRate()).to.equal(newBaseRate);
    });

    it("should revert when called by non-admin", async function () {
      await expect(
        model.connect(nonAdmin).setBaseRate(ethers.parseUnits("0.01", 18))
      ).to.be.revertedWith("Not admin");
    });
  });

  describe("setMultiplier", function () {
    it("should update multiplier and emit event with old and new values", async function () {
      const newMultiplier = ethers.parseUnits("0.2", 18);
      await expect(model.connect(admin).setMultiplier(newMultiplier))
        .to.emit(model, "RateParametersUpdated")
        .withArgs(
          BASE_RATE, BASE_RATE,
          MULTIPLIER, newMultiplier,
          JUMP_MULTIPLIER, JUMP_MULTIPLIER,
          KINK, KINK
        );
      expect(await model.multiplier()).to.equal(newMultiplier);
    });

    it("should revert when called by non-admin", async function () {
      await expect(
        model.connect(nonAdmin).setMultiplier(ethers.parseUnits("0.01", 18))
      ).to.be.revertedWith("Not admin");
    });
  });

  describe("setJumpMultiplier", function () {
    it("should update jump multiplier and emit event with old and new values", async function () {
      const newJumpMultiplier = ethers.parseUnits("3", 18);
      await expect(model.connect(admin).setJumpMultiplier(newJumpMultiplier))
        .to.emit(model, "RateParametersUpdated")
        .withArgs(
          BASE_RATE, BASE_RATE,
          MULTIPLIER, MULTIPLIER,
          JUMP_MULTIPLIER, newJumpMultiplier,
          KINK, KINK
        );
      expect(await model.jumpMultiplier()).to.equal(newJumpMultiplier);
    });

    it("should revert when called by non-admin", async function () {
      await expect(
        model.connect(nonAdmin).setJumpMultiplier(ethers.parseUnits("1", 18))
      ).to.be.revertedWith("Not admin");
    });
  });

  describe("setKink", function () {
    it("should update kink and emit event with old and new values", async function () {
      const newKink = ethers.parseUnits("0.7", 18);
      await expect(model.connect(admin).setKink(newKink))
        .to.emit(model, "RateParametersUpdated")
        .withArgs(
          BASE_RATE, BASE_RATE,
          MULTIPLIER, MULTIPLIER,
          JUMP_MULTIPLIER, JUMP_MULTIPLIER,
          KINK, newKink
        );
      expect(await model.kink()).to.equal(newKink);
    });

    it("should revert when called by non-admin", async function () {
      await expect(
        model.connect(nonAdmin).setKink(ethers.parseUnits("0.9", 18))
      ).to.be.revertedWith("Not admin");
    });
  });

  describe("updateParams", function () {
    it("should update all parameters and emit event with old and new values", async function () {
      const newBase = ethers.parseUnits("0.03", 18);
      const newMult = ethers.parseUnits("0.15", 18);
      const newJump = ethers.parseUnits("2.5", 18);
      const newKink = ethers.parseUnits("0.75", 18);

      await expect(model.connect(admin).updateParams(newBase, newMult, newJump, newKink))
        .to.emit(model, "RateParametersUpdated")
        .withArgs(
          BASE_RATE, newBase,
          MULTIPLIER, newMult,
          JUMP_MULTIPLIER, newJump,
          KINK, newKink
        );

      expect(await model.baseRate()).to.equal(newBase);
      expect(await model.multiplier()).to.equal(newMult);
      expect(await model.jumpMultiplier()).to.equal(newJump);
      expect(await model.kink()).to.equal(newKink);
    });

    it("should revert when called by non-admin", async function () {
      await expect(
        model.connect(nonAdmin).updateParams(1, 1, 1, 1)
      ).to.be.revertedWith("Not admin");
    });
  });

  describe("Access control across all setters", function () {
    it("should allow admin to call all setters", async function () {
      // All should succeed without revert
      await model.connect(admin).setBaseRate(1);
      await model.connect(admin).setMultiplier(2);
      await model.connect(admin).setJumpMultiplier(3);
      await model.connect(admin).setKink(4);
      await model.connect(admin).updateParams(5, 6, 7, 8);

      const params = await model.getParameters();
      expect(params[0]).to.equal(5n);
      expect(params[1]).to.equal(6n);
      expect(params[2]).to.equal(7n);
      expect(params[3]).to.equal(8n);
    });
  });
});