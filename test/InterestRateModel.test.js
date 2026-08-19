const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("InterestRateModel", function () {
  let model;
  let admin, other;

  beforeEach(async function () {
    [admin, other] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("InterestRateModel");
    // baseRate=1%, multiplier=5%, jumpMultiplier=20%, kink=80%
    model = await Factory.deploy(
      ethers.parseEther("0.01"),
      ethers.parseEther("0.05"),
      ethers.parseEther("0.20"),
      ethers.parseEther("0.80")
    );
    await model.waitForDeployment();
  });

  it("should emit RateParamsUpdated with old and new values on updateParams", async function () {
    const newBase = ethers.parseEther("0.02");
    const newMult = ethers.parseEther("0.06");
    const newJump = ethers.parseEther("0.25");
    const newKink = ethers.parseEther("0.75");

    await expect(model.connect(admin).updateParams(newBase, newMult, newJump, newKink))
      .to.emit(model, "RateParamsUpdated")
      .withArgs(
        ethers.parseEther("0.01"), newBase,
        ethers.parseEther("0.05"), newMult,
        ethers.parseEther("0.20"), newJump,
        ethers.parseEther("0.80"), newKink
      );

    const params = await model.getParameters();
    expect(params.baseRate).to.equal(newBase);
    expect(params.multiplier).to.equal(newMult);
    expect(params.jumpMultiplier).to.equal(newJump);
    expect(params.kink).to.equal(newKink);
  });

  it("should revert when non-admin calls updateParams", async function () {
    await expect(
      model.connect(other).updateParams(0, 0, 0, 0)
    ).to.be.revertedWith("Not admin");
  });

  it("should return all parameters via getParameters()", async function () {
    const params = await model.getParameters();
    expect(params.baseRate).to.equal(ethers.parseEther("0.01"));
    expect(params.multiplier).to.equal(ethers.parseEther("0.05"));
    expect(params.jumpMultiplier).to.equal(ethers.parseEther("0.20"));
    expect(params.kink).to.equal(ethers.parseEther("0.80"));
  });
});
