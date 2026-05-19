const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("InterestRateModel", function () {
  let InterestRateModel;
  let interestRateModel;
  let owner;
  let nonAdmin;

  beforeEach(async function () {
    [owner, nonAdmin] = await ethers.getSigners();
    InterestRateModel = await ethers.getContractFactory("InterestRateModel");
    // Deploy with: _baseRate = 0.05e18, _multiplier = 0.15e18, _jumpMultiplier = 1.0e18, _kink = 0.8e18
    interestRateModel = await InterestRateModel.deploy(
      ethers.parseEther("0.05"),
      ethers.parseEther("0.15"),
      ethers.parseEther("1.0"),
      ethers.parseEther("0.8")
    );
  });

  describe("Deployment", function () {
    it("should set initial parameters correctly", async function () {
      const params = await interestRateModel.getParameters();
      expect(params.baseRate).to.equal(ethers.parseEther("0.05"));
      expect(params.multiplier).to.equal(ethers.parseEther("0.15"));
      expect(params.jumpMultiplier).to.equal(ethers.parseEther("1.0"));
      expect(params.kink).to.equal(ethers.parseEther("0.8"));
    });
  });

  describe("Parameter Updates and Events", function () {
    it("should allow admin to update all parameters and emit event", async function () {
      const tx = await interestRateModel.updateParams(
        ethers.parseEther("0.06"),
        ethers.parseEther("0.16"),
        ethers.parseEther("1.1"),
        ethers.parseEther("0.85")
      );

      await expect(tx)
        .to.emit(interestRateModel, "RateParametersUpdated")
        .withArgs(
          ethers.parseEther("0.05"),
          ethers.parseEther("0.06"),
          ethers.parseEther("0.15"),
          ethers.parseEther("0.16"),
          ethers.parseEther("1.0"),
          ethers.parseEther("1.1"),
          ethers.parseEther("0.8"),
          ethers.parseEther("0.85")
        );

      const params = await interestRateModel.getParameters();
      expect(params.baseRate).to.equal(ethers.parseEther("0.06"));
      expect(params.multiplier).to.equal(ethers.parseEther("0.16"));
      expect(params.jumpMultiplier).to.equal(ethers.parseEther("1.1"));
      expect(params.kink).to.equal(ethers.parseEther("0.85"));
    });

    it("should revert if non-admin tries to update parameters", async function () {
      await expect(
        interestRateModel.connect(nonAdmin).updateParams(
          ethers.parseEther("0.06"),
          ethers.parseEther("0.16"),
          ethers.parseEther("1.1"),
          ethers.parseEther("0.85")
        )
      ).to.be.revertedWith("Not admin");
    });

    it("should allow individual setters and emit event", async function () {
      // Base Rate
      let tx = await interestRateModel.setBaseRate(ethers.parseEther("0.07"));
      await expect(tx)
        .to.emit(interestRateModel, "RateParametersUpdated")
        .withArgs(
          ethers.parseEther("0.05"),
          ethers.parseEther("0.07"),
          ethers.parseEther("0.15"),
          ethers.parseEther("0.15"),
          ethers.parseEther("1.0"),
          ethers.parseEther("1.0"),
          ethers.parseEther("0.8"),
          ethers.parseEther("0.8")
        );

      // Multiplier
      tx = await interestRateModel.setMultiplier(ethers.parseEther("0.20"));
      await expect(tx)
        .to.emit(interestRateModel, "RateParametersUpdated")
        .withArgs(
          ethers.parseEther("0.07"),
          ethers.parseEther("0.07"),
          ethers.parseEther("0.15"),
          ethers.parseEther("0.20"),
          ethers.parseEther("1.0"),
          ethers.parseEther("1.0"),
          ethers.parseEther("0.8"),
          ethers.parseEther("0.8")
        );

      // Jump Multiplier
      tx = await interestRateModel.setJumpMultiplier(ethers.parseEther("1.5"));
      await expect(tx)
        .to.emit(interestRateModel, "RateParametersUpdated")
        .withArgs(
          ethers.parseEther("0.07"),
          ethers.parseEther("0.07"),
          ethers.parseEther("0.20"),
          ethers.parseEther("0.20"),
          ethers.parseEther("1.0"),
          ethers.parseEther("1.5"),
          ethers.parseEther("0.8"),
          ethers.parseEther("0.8")
        );

      // Kink
      tx = await interestRateModel.setKink(ethers.parseEther("0.75"));
      await expect(tx)
        .to.emit(interestRateModel, "RateParametersUpdated")
        .withArgs(
          ethers.parseEther("0.07"),
          ethers.parseEther("0.07"),
          ethers.parseEther("0.20"),
          ethers.parseEther("0.20"),
          ethers.parseEther("1.5"),
          ethers.parseEther("1.5"),
          ethers.parseEther("0.8"),
          ethers.parseEther("0.75")
        );
    });

    it("should revert if non-admin tries to call individual setters", async function () {
      await expect(
        interestRateModel.connect(nonAdmin).setBaseRate(ethers.parseEther("0.07"))
      ).to.be.revertedWith("Not admin");

      await expect(
        interestRateModel.connect(nonAdmin).setMultiplier(ethers.parseEther("0.20"))
      ).to.be.revertedWith("Not admin");

      await expect(
        interestRateModel.connect(nonAdmin).setJumpMultiplier(ethers.parseEther("1.5"))
      ).to.be.revertedWith("Not admin");

      await expect(
        interestRateModel.connect(nonAdmin).setKink(ethers.parseEther("0.75"))
      ).to.be.revertedWith("Not admin");
    });
  });
});
