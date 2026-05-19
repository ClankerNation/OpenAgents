const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("InterestRateModel", function () {
  let interestRateModel;
  let admin, nonAdmin;

  const BASE_RATE = ethers.utils.parseEther("0.02"); // 2%
  const MULTIPLIER = ethers.utils.parseEther("0.1"); // 10%
  const JUMP_MULTIPLIER = ethers.utils.parseEther("0.5"); // 50%
  const KINK = ethers.utils.parseEther("0.8"); // 80%

  beforeEach(async function () {
    [admin, nonAdmin] = await ethers.getSigners();

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
    it("should return all current parameters as a struct", async function () {
      const params = await interestRateModel.getParameters();

      expect(params.baseRate).to.equal(BASE_RATE);
      expect(params.multiplier).to.equal(MULTIPLIER);
      expect(params.jumpMultiplier).to.equal(JUMP_MULTIPLIER);
      expect(params.kink).to.equal(KINK);
    });

    it("should reflect updated parameters", async function () {
      const newBase = ethers.utils.parseEther("0.05");
      const newMult = ethers.utils.parseEther("0.15");
      const newJump = ethers.utils.parseEther("0.8");
      const newKink = ethers.utils.parseEther("0.9");

      await interestRateModel.updateParams(newBase, newMult, newJump, newKink);

      const params = await interestRateModel.getParameters();
      expect(params.baseRate).to.equal(newBase);
      expect(params.multiplier).to.equal(newMult);
      expect(params.jumpMultiplier).to.equal(newJump);
      expect(params.kink).to.equal(newKink);
    });
  });

  describe("updateParams", function () {
    it("should emit RateParamsUpdated with old and new values", async function () {
      const newBase = ethers.utils.parseEther("0.03");
      const newMult = ethers.utils.parseEther("0.12");
      const newJump = ethers.utils.parseEther("0.6");
      const newKink = ethers.utils.parseEther("0.85");

      await expect(
        interestRateModel.updateParams(newBase, newMult, newJump, newKink)
      )
        .to.emit(interestRateModel, "RateParamsUpdated")
        .withArgs(
          [BASE_RATE, MULTIPLIER, JUMP_MULTIPLIER, KINK], // old params
          [newBase, newMult, newJump, newKink]              // new params
        );
    });

    it("should update storage after emitting event", async function () {
      const newBase = ethers.utils.parseEther("0.04");

      await interestRateModel.updateParams(
        newBase,
        MULTIPLIER,
        JUMP_MULTIPLIER,
        KINK
      );

      expect(await interestRateModel.baseRate()).to.equal(newBase);
      // Other params unchanged
      expect(await interestRateModel.multiplier()).to.equal(MULTIPLIER);
    });

    it("should revert when called by non-admin", async function () {
      const newBase = ethers.utils.parseEther("0.03");

      await expect(
        interestRateModel.connect(nonAdmin).updateParams(
          newBase, MULTIPLIER, JUMP_MULTIPLIER, KINK
        )
      ).to.be.revertedWith("Not admin");
    });

    it("should allow multiple parameter updates from same admin", async function () {
      // First update
      const firstBase = ethers.utils.parseEther("0.03");
      await interestRateModel.updateParams(
        firstBase, MULTIPLIER, JUMP_MULTIPLIER, KINK
      );

      // Second update — old params should reflect first update
      const secondBase = ethers.utils.parseEther("0.04");
      await expect(
        interestRateModel.updateParams(
          secondBase, MULTIPLIER, JUMP_MULTIPLIER, KINK
        )
      )
        .to.emit(interestRateModel, "RateParamsUpdated")
        .withArgs(
          [firstBase, MULTIPLIER, JUMP_MULTIPLIER, KINK],
          [secondBase, MULTIPLIER, JUMP_MULTIPLIER, KINK]
        );

      expect(await interestRateModel.baseRate()).to.equal(secondBase);
    });

    it("should emit old params matching what getParameters() returned before update", async function () {
      // Verify getParameters matches old values we'll check in event
      const paramsBefore = await interestRateModel.getParameters();
      expect(paramsBefore.baseRate).to.equal(BASE_RATE);

      const newBase = ethers.utils.parseEther("0.07");

      const tx = await interestRateModel.updateParams(
        newBase, MULTIPLIER, JUMP_MULTIPLIER, KINK
      );
      const receipt = await tx.wait();

      // Parse the event from receipt
      const event = receipt.events.find(e => e.event === "RateParamsUpdated");
      const [oldParams, newParams] = event.args;

      expect(oldParams.baseRate).to.equal(BASE_RATE);
      expect(newParams.baseRate).to.equal(newBase);
    });
  });

  describe("getBorrowRate", function () {
    it("should compute borrow rate below kink", async function () {
      const totalBorrowed = ethers.utils.parseEther("500");
      const totalDeposits = ethers.utils.parseEther("1000");

      const rate = await interestRateModel.getBorrowRate(totalBorrowed, totalDeposits);
      expect(rate).to.be.gt(0);
    });

    it("should compute borrow rate above kink", async function () {
      const totalBorrowed = ethers.utils.parseEther("900");
      const totalDeposits = ethers.utils.parseEther("1000");

      const rate = await interestRateModel.getBorrowRate(totalBorrowed, totalDeposits);
      expect(rate).to.be.gt(0);
    });
  });
});
