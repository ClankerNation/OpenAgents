const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("InterestRateModel", function () {
  let model;
  let admin;

  const BASE_RATE = ethers.utils.parseEther("0.02");       // 2%
  const MULTIPLIER = ethers.utils.parseEther("0.1");       // 10%
  const JUMP_MULTIPLIER = ethers.utils.parseEther("1.0");  // 100%
  const KINK = ethers.utils.parseEther("0.8");             // 80%

  beforeEach(async function () {
    [admin] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("InterestRateModel");
    model = await Factory.deploy(BASE_RATE, MULTIPLIER, JUMP_MULTIPLIER, KINK);
    await model.deployed();
  });

  describe("getParameters", function () {
    it("returns constructor values", async function () {
      const params = await model.getParameters();
      expect(params.baseRate).to.equal(BASE_RATE);
      expect(params.multiplier).to.equal(MULTIPLIER);
      expect(params.jumpMultiplier).to.equal(JUMP_MULTIPLIER);
      expect(params.kink).to.equal(KINK);
    });

    it("reflects changes after setBaseRatePerYear", async function () {
      const newRate = ethers.utils.parseEther("0.05");
      await model.setBaseRatePerYear(newRate);

      const params = await model.getParameters();
      expect(params.baseRate).to.equal(newRate);
      expect(params.multiplier).to.equal(MULTIPLIER);
    });

    it("reflects changes after setMultiplierPerYear", async function () {
      const newMult = ethers.utils.parseEther("0.2");
      await model.setMultiplierPerYear(newMult);

      const params = await model.getParameters();
      expect(params.multiplier).to.equal(newMult);
      expect(params.baseRate).to.equal(BASE_RATE);
    });

    it("reflects changes after setJumpMultiplierPerYear", async function () {
      const newJump = ethers.utils.parseEther("2.0");
      await model.setJumpMultiplierPerYear(newJump);

      const params = await model.getParameters();
      expect(params.jumpMultiplier).to.equal(newJump);
      expect(params.baseRate).to.equal(BASE_RATE);
    });
  });

  describe("RateParametersUpdated event", function () {
    it("emits on setBaseRatePerYear with old and new values", async function () {
      const newRate = ethers.utils.parseEther("0.05");

      await expect(model.setBaseRatePerYear(newRate))
        .to.emit(model, "RateParametersUpdated")
        .withArgs(
          BASE_RATE,       // oldBaseRate
          newRate,          // newBaseRate
          MULTIPLIER,       // oldMultiplier
          MULTIPLIER,       // newMultiplier (unchanged)
          JUMP_MULTIPLIER,  // oldJumpMultiplier
          JUMP_MULTIPLIER   // newJumpMultiplier (unchanged)
        );
    });

    it("emits on setMultiplierPerYear with old and new values", async function () {
      const newMult = ethers.utils.parseEther("0.2");

      await expect(model.setMultiplierPerYear(newMult))
        .to.emit(model, "RateParametersUpdated")
        .withArgs(
          BASE_RATE,        // oldBaseRate
          BASE_RATE,        // newBaseRate (unchanged)
          MULTIPLIER,       // oldMultiplier
          newMult,          // newMultiplier
          JUMP_MULTIPLIER,  // oldJumpMultiplier
          JUMP_MULTIPLIER   // newJumpMultiplier (unchanged)
        );
    });

    it("emits on setJumpMultiplierPerYear with old and new values", async function () {
      const newJump = ethers.utils.parseEther("2.0");

      await expect(model.setJumpMultiplierPerYear(newJump))
        .to.emit(model, "RateParametersUpdated")
        .withArgs(
          BASE_RATE,        // oldBaseRate
          BASE_RATE,        // newBaseRate (unchanged)
          MULTIPLIER,       // oldMultiplier
          MULTIPLIER,       // newMultiplier (unchanged)
          JUMP_MULTIPLIER,  // oldJumpMultiplier
          newJump           // newJumpMultiplier
        );
    });

    it("emits event before state update", async function () {
      const newRate = ethers.utils.parseEther("0.05");

      const tx = await model.setBaseRatePerYear(newRate);
      const receipt = await tx.wait();

      // Event should be in the logs
      const event = receipt.events.find(e => e.event === "RateParametersUpdated");
      expect(event).to.not.be.undefined;
      expect(event.args.oldBaseRate).to.equal(BASE_RATE);
      expect(event.args.newBaseRate).to.equal(newRate);

      // State should reflect the new value
      expect(await model.baseRate()).to.equal(newRate);
    });

    it("not emitted on updateParams (uses legacy event)", async function () {
      const newRate = ethers.utils.parseEther("0.03");
      const tx = await model.updateParams(newRate, MULTIPLIER, JUMP_MULTIPLIER, KINK);
      const receipt = await tx.wait();

      const events = receipt.events.filter(e => e.event === "RateParametersUpdated");
      expect(events.length).to.equal(0);
    });
  });

  describe("Authorization", function () {
    it("reverts when non-admin sets base rate", async function () {
      const [, nonAdmin] = await ethers.getSigners();
      await expect(
        model.connect(nonAdmin).setBaseRatePerYear(0)
      ).to.be.revertedWith("Not admin");
    });

    it("reverts when non-admin sets multiplier", async function () {
      const [, nonAdmin] = await ethers.getSigners();
      await expect(
        model.connect(nonAdmin).setMultiplierPerYear(0)
      ).to.be.revertedWith("Not admin");
    });

    it("reverts when non-admin sets jump multiplier", async function () {
      const [, nonAdmin] = await ethers.getSigners();
      await expect(
        model.connect(nonAdmin).setJumpMultiplierPerYear(0)
      ).to.be.revertedWith("Not admin");
    });
  });
});
