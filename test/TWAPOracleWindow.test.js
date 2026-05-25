const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("TWAPOracle hardened window", function () {
  let pair;
  let oracle;
  const windowSize = 30 * 60;
  const price100 = ethers.parseEther("100");
  const price200 = ethers.parseEther("200");
  const price300 = ethers.parseEther("300");

  beforeEach(async function () {
    [, pair] = await ethers.getSigners();
    const TWAPOracle = await ethers.getContractFactory("TWAPOracle");
    oracle = await TWAPOracle.deploy(pair.address);
  });

  it("enforces a configurable 30 minute minimum window", async function () {
    expect(await oracle.windowSize()).to.equal(windowSize);

    await expect(oracle.setWindowSize(windowSize - 1)).to.be.revertedWith("Window too short");

    await expect(oracle.setWindowSize(windowSize * 2))
      .to.emit(oracle, "WindowUpdated")
      .withArgs(windowSize * 2);
  });

  it("allows only one observation per block", async function () {
    const TWAPDoubleRecorder = await ethers.getContractFactory("TWAPDoubleRecorder");
    const recorder = await TWAPDoubleRecorder.deploy();

    await expect(recorder.recordTwice(oracle, price100, price200)).to.be.revertedWith(
      "Observation already recorded",
    );
  });

  it("computes the cumulative-price TWAP over the configured window", async function () {
    await oracle.recordObservation(price100);
    await time.increase(windowSize);
    await oracle.recordObservation(price200);

    expect(await oracle.getTWAP()).to.equal(price100);

    await time.increase(windowSize);
    await oracle.recordObservation(price300);

    expect(await oracle.getTWAP()).to.equal(price200);
  });

  it("reverts when the latest price is stale", async function () {
    await oracle.recordObservation(price100);
    await time.increase(windowSize);
    await oracle.recordObservation(price200);

    await time.increase(windowSize + 1);

    await expect(oracle.getTWAP()).to.be.revertedWith("Stale price");
    await expect(oracle.getLatestPrice()).to.be.revertedWith("Stale price");
  });

  it("requires observations to cover the full window", async function () {
    await oracle.recordObservation(price100);
    await time.increase(windowSize - 10);
    await oracle.recordObservation(price200);

    await expect(oracle.getTWAP()).to.be.revertedWith("Window not covered");
  });
});
