const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("InterestRateModel parameter events", function () {
  let owner;
  let other;
  let model;

  const initialParams = {
    baseRate: 1n,
    multiplier: 2n,
    jumpMultiplier: 3n,
    kink: ethers.parseEther("0.8"),
  };

  const newParams = {
    baseRate: 11n,
    multiplier: 22n,
    jumpMultiplier: 33n,
    kink: ethers.parseEther("0.9"),
  };

  beforeEach(async function () {
    [owner, other] = await ethers.getSigners();
    const InterestRateModel = await ethers.getContractFactory("InterestRateModel");
    model = await InterestRateModel.deploy(
      initialParams.baseRate,
      initialParams.multiplier,
      initialParams.jumpMultiplier,
      initialParams.kink,
    );
  });

  it("returns all parameters in a single getter", async function () {
    const params = await model.getParameters();

    expect(params.baseRate).to.equal(initialParams.baseRate);
    expect(params.multiplier).to.equal(initialParams.multiplier);
    expect(params.jumpMultiplier).to.equal(initialParams.jumpMultiplier);
    expect(params.kink).to.equal(initialParams.kink);
  });

  it("emits old and new values on parameter updates", async function () {
    await expect(
      model.updateParams(
        newParams.baseRate,
        newParams.multiplier,
        newParams.jumpMultiplier,
        newParams.kink,
      ),
    )
      .to.emit(model, "RateParametersUpdated")
      .withArgs(
        initialParams.baseRate,
        newParams.baseRate,
        initialParams.multiplier,
        newParams.multiplier,
        initialParams.jumpMultiplier,
        newParams.jumpMultiplier,
        initialParams.kink,
        newParams.kink,
      )
      .and.to.emit(model, "RateParamsUpdated")
      .withArgs(
        newParams.baseRate,
        newParams.multiplier,
        newParams.jumpMultiplier,
        newParams.kink,
      );

    const params = await model.getParameters();
    expect(params.baseRate).to.equal(newParams.baseRate);
    expect(params.multiplier).to.equal(newParams.multiplier);
    expect(params.jumpMultiplier).to.equal(newParams.jumpMultiplier);
    expect(params.kink).to.equal(newParams.kink);
  });

  it("keeps parameter updates admin-only", async function () {
    await expect(
      model.connect(other).updateParams(
        newParams.baseRate,
        newParams.multiplier,
        newParams.jumpMultiplier,
        newParams.kink,
      ),
    ).to.be.revertedWith("Not admin");
  });
});
