const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("InterestRateModel", function () {
  let model;
  let admin, user;

  const PRECISION = ethers.BigNumber.from("1000000000000000000");

  beforeEach(async function () {
    [admin, user] = await ethers.getSigners();
    const InterestRateModel = await ethers.getContractFactory("InterestRateModel");
    model = await InterestRateModel.deploy(
      ethers.utils.parseEther("0.05"),
      ethers.utils.parseEther("0.1"),
      ethers.utils.parseEther("1.0"),
      ethers.utils.parseEther("0.8")
    );
    await model.deployed();
  });

  describe("getParameters", function () {
    it("should return all rate parameters", async function () {
      const params = await model.getParameters();
      expect(params.baseRate).to.equal(ethers.utils.parseEther("0.05"));
      expect(params.multiplier).to.equal(ethers.utils.parseEther("0.1"));
      expect(params.jumpMultiplier).to.equal(ethers.utils.parseEther("1.0"));
      expect(params.kink).to.equal(ethers.utils.parseEther("0.8"));
    });
  });

  describe("updateParams", function () {
    it("should emit RateParametersUpdated with old and new values", async function () {
      const newBase = ethers.utils.parseEther("0.06");
      const newMulti = ethers.utils.parseEther("0.12");
      const newJump = ethers.utils.parseEther("1.5");
      const newKink = ethers.utils.parseEther("0.85");

      await expect(model.connect(admin).updateParams(newBase, newMulti, newJump, newKink))
        .to.emit(model, "RateParametersUpdated")
        .withArgs(
          ethers.utils.parseEther("0.05"), newBase,
          ethers.utils.parseEther("0.1"), newMulti,
          ethers.utils.parseEther("1.0"), newJump,
          ethers.utils.parseEther("0.8"), newKink
        );
    });

    it("should update stored values after emit", async function () {
      await model.connect(admin).updateParams(
        ethers.utils.parseEther("0.07"),
        ethers.utils.parseEther("0.15"),
        ethers.utils.parseEther("2.0"),
        ethers.utils.parseEther("0.9")
      );

      const params = await model.getParameters();
      expect(params.baseRate).to.equal(ethers.utils.parseEther("0.07"));
      expect(params.multiplier).to.equal(ethers.utils.parseEther("0.15"));
      expect(params.jumpMultiplier).to.equal(ethers.utils.parseEther("2.0"));
      expect(params.kink).to.equal(ethers.utils.parseEther("0.9"));
    });

    it("should reject non-admin callers", async function () {
      await expect(
        model.connect(user).updateParams(
          ethers.utils.parseEther("0.06"),
          ethers.utils.parseEther("0.12"),
          ethers.utils.parseEther("1.5"),
          ethers.utils.parseEther("0.85")
        )
      ).to.be.revertedWith("Not admin");
    });

    it("should emit event with matching old and new values when params unchanged", async function () {
      const base = await model.baseRate();
      const multi = await model.multiplier();
      const jump = await model.jumpMultiplier();
      const k = await model.kink();

      await expect(model.connect(admin).updateParams(base, multi, jump, k))
        .to.emit(model, "RateParametersUpdated")
        .withArgs(base, base, multi, multi, jump, jump, k, k);
    });
  });

  describe("getBorrowRate and getSupplyRate", function () {
    it("should work after parameter update", async function () {
      await model.connect(admin).updateParams(
        ethers.utils.parseEther("0.1"),
        ethers.utils.parseEther("0.2"),
        ethers.utils.parseEther("2.0"),
        ethers.utils.parseEther("0.8")
      );

      const borrowRate = await model.getBorrowRate(
        ethers.utils.parseEther("500"),
        ethers.utils.parseEther("1000")
      );
      expect(borrowRate).to.be.gt(0);
    });
  });
});
