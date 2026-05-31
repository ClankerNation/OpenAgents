const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("InterestRateModel", function () {
  async function deployModel(params) {
    const InterestRateModel = await ethers.getContractFactory("InterestRateModel");
    const model = await InterestRateModel.deploy(
      params.baseRate,
      params.multiplier,
      params.jumpMultiplier,
      params.kink
    );

    if (model.waitForDeployment) {
      await model.waitForDeployment();
    } else {
      await model.deployed();
    }

    return model;
  }

  it("emits compatibility and old/new events when params are updated", async function () {
    const initial = {
      baseRate: 100,
      multiplier: 200,
      jumpMultiplier: 300,
      kink: ethers.parseUnits ? ethers.parseUnits("0.8", 18) : ethers.utils.parseUnits("0.8", 18),
    };

    const next = {
      baseRate: 150,
      multiplier: 250,
      jumpMultiplier: 350,
      kink: ethers.parseUnits ? ethers.parseUnits("0.9", 18) : ethers.utils.parseUnits("0.9", 18),
    };

    const model = await deployModel(initial);

    await expect(model.updateParams(next.baseRate, next.multiplier, next.jumpMultiplier, next.kink))
      .to.emit(model, "RateParamsUpdated")
      .withArgs(next.baseRate, next.multiplier, next.jumpMultiplier, next.kink)
      .and.to.emit(model, "RateParametersUpdated")
      .withArgs(
        initial.baseRate,
        next.baseRate,
        initial.multiplier,
        next.multiplier,
        initial.jumpMultiplier,
        next.jumpMultiplier,
        initial.kink,
        next.kink
      );
  });

  it("returns all parameters from getParameters()", async function () {
    const params = {
      baseRate: 111,
      multiplier: 222,
      jumpMultiplier: 333,
      kink: ethers.parseUnits ? ethers.parseUnits("0.75", 18) : ethers.utils.parseUnits("0.75", 18),
    };

    const model = await deployModel(params);
    const current = await model.getParameters();

    expect(current.baseRate).to.equal(params.baseRate);
    expect(current.multiplier).to.equal(params.multiplier);
    expect(current.jumpMultiplier).to.equal(params.jumpMultiplier);
    expect(current.kink).to.equal(params.kink);
  });
});
