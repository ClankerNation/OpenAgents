const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("InterestRateModel", function () {
  let model;
  let owner, other;

  beforeEach(async function () {
    [owner, other] = await ethers.getSigners();
    const Model = await ethers.getContractFactory("InterestRateModel");
    model = await Model.deploy(
      ethers.parseEther("0.02"),   // 2% base rate
      ethers.parseEther("0.1"),    // 10% multiplier
      ethers.parseEther("0.5"),    // 50% jump multiplier
      ethers.parseEther("0.8")     // 80% kink
    );
    await model.waitForDeployment();
  });

  it("emits RateParametersUpdated on updateParams", async function () {
    const oldBase = ethers.parseEther("0.02");
    const newBase = ethers.parseEther("0.05");

    await expect(model.updateParams(newBase, ethers.parseEther("0.1"), ethers.parseEther("0.5"), ethers.parseEther("0.8")))
      .to.emit(model, "RateParametersUpdated")
      .withArgs(oldBase, newBase, ethers.parseEther("0.1"), ethers.parseEther("0.1"), ethers.parseEther("0.5"), ethers.parseEther("0.5"), ethers.parseEther("0.8"), ethers.parseEther("0.8"));
  });

  it("getParameters returns current values", async function () {
    const params = await model.getParameters();
    expect(params.baseRate).to.equal(ethers.parseEther("0.02"));
    expect(params.multiplier).to.equal(ethers.parseEther("0.1"));
    expect(params.jumpMultiplier).to.equal(ethers.parseEther("0.5"));
    expect(params.kink).to.equal(ethers.parseEther("0.8"));
  });

  it("reverts if non-admin calls updateParams", async function () {
    await expect(
      model.connect(other).updateParams(0, 0, 0, 0)
    ).to.be.revertedWith("Not admin");
  });

  it("updates parameters correctly", async function () {
    await model.updateParams(
      ethers.parseEther("0.03"),
      ethers.parseEther("0.15"),
      ethers.parseEther("0.6"),
      ethers.parseEther("0.85")
    );
    const params = await model.getParameters();
    expect(params.baseRate).to.equal(ethers.parseEther("0.03"));
    expect(params.multiplier).to.equal(ethers.parseEther("0.15"));
  });
});
