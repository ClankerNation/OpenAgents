const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("InterestRateModel utilization cap", function () {
  let model;
  const precision = ethers.parseEther("1");
  const minBaseRate = ethers.parseEther("0.001");
  const maxBaseRate = ethers.parseEther("0.5");
  const baseRate = ethers.parseEther("0.01");
  const multiplier = ethers.parseEther("0.1");
  const jumpMultiplier = ethers.parseEther("0.5");
  const kink = ethers.parseEther("0.8");

  beforeEach(async function () {
    const InterestRateModel = await ethers.getContractFactory("InterestRateModel");
    model = await InterestRateModel.deploy(baseRate, multiplier, jumpMultiplier, kink);
  });

  it("returns the base rate at 0% utilization", async function () {
    expect(await model.getInterestRate(0, ethers.parseEther("100"))).to.equal(baseRate);
  });

  it("calculates the normal curve at 50% utilization", async function () {
    const expected = baseRate + (ethers.parseEther("0.5") * multiplier) / precision;

    expect(await model.getInterestRate(ethers.parseEther("50"), ethers.parseEther("100"))).to.equal(
      expected,
    );
  });

  it("calculates the jump curve at 99% utilization", async function () {
    const utilization = ethers.parseEther("0.99");
    const normalRate = baseRate + (kink * multiplier) / precision;
    const jumpRate = ((utilization - kink) * jumpMultiplier) / (precision - kink);

    expect(await model.getInterestRate(ethers.parseEther("99"), ethers.parseEther("100"))).to.equal(
      normalRate + jumpRate,
    );
  });

  it("caps 100% utilization at 99.99% without dividing by zero", async function () {
    const cappedUtilization = await model.MAX_UTILIZATION();
    const normalRate = baseRate + (kink * multiplier) / precision;
    const jumpRate = ((cappedUtilization - kink) * jumpMultiplier) / (precision - kink);

    expect(await model.getUtilization(ethers.parseEther("100"), ethers.parseEther("100"))).to.equal(
      cappedUtilization,
    );
    expect(await model.getInterestRate(ethers.parseEther("100"), ethers.parseEther("100"))).to.equal(
      normalRate + jumpRate,
    );
  });

  it("bounds base rate and kink parameters", async function () {
    const InterestRateModel = await ethers.getContractFactory("InterestRateModel");

    await expect(
      InterestRateModel.deploy(minBaseRate - 1n, multiplier, jumpMultiplier, kink),
    ).to.be.revertedWith("Base rate out of bounds");

    await expect(
      model.updateParams(maxBaseRate + 1n, multiplier, jumpMultiplier, kink),
    ).to.be.revertedWith("Base rate out of bounds");

    await expect(
      model.updateParams(baseRate, multiplier, jumpMultiplier, precision),
    ).to.be.revertedWith("Invalid kink");
  });
});
