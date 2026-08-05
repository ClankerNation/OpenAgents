const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TWAPOracle hardening", function () {
  const MIN_WINDOW = 30n * 60n;

  async function deploy() {
    const [admin] = await ethers.getSigners();
    const TWAPOracle = await ethers.getContractFactory("TWAPOracle");
    const oracle = await TWAPOracle.deploy(admin.address);
    await oracle.waitForDeployment();
    return { oracle, admin };
  }

  async function recordAt(oracle, timestamp, price) {
    await ethers.provider.send("evm_setNextBlockTimestamp", [Number(timestamp)]);
    await oracle.recordObservation(price);
  }

  it("enforces a thirty-minute minimum window", async function () {
    const { oracle } = await deploy();
    expect(await oracle.windowSize()).to.equal(MIN_WINDOW);
    await expect(oracle.setWindowSize(MIN_WINDOW - 1n)).to.be.revertedWith("Window too short");
    await oracle.setWindowSize(MIN_WINDOW + 1n);
    expect(await oracle.windowSize()).to.equal(MIN_WINDOW + 1n);
  });

  it("rejects multiple observations in the same block", async function () {
    const { oracle } = await deploy();
    const SameBlockRecorder = await ethers.getContractFactory("SameBlockRecorder");
    const recorder = await SameBlockRecorder.deploy();
    await recorder.waitForDeployment();

    await expect(recorder.recordTwice(await oracle.getAddress(), 100n, 200n)).to.be.revertedWith(
      "Same block"
    );
    expect(await oracle.getObservationCount()).to.equal(0n);
  });

  it("computes an exact cumulative TWAP and rejects stale observations", async function () {
    const { oracle } = await deploy();
    await oracle.recordObservation(100n);
    const first = await ethers.provider.getBlock("latest");
    const firstTimestamp = BigInt(first.timestamp);

    await recordAt(oracle, firstTimestamp + 900n, 100n);
    await recordAt(oracle, firstTimestamp + 1_800n, 200n);
    await recordAt(oracle, firstTimestamp + 2_700n, 200n);

    expect(await oracle.getTWAP()).to.equal(150n);

    await ethers.provider.send("evm_setNextBlockTimestamp", [
      Number(firstTimestamp + 2_700n + MIN_WINDOW + 1n),
    ]);
    await ethers.provider.send("evm_mine");
    await expect(oracle.getTWAP()).to.be.revertedWith("Stale observations");
  });
});
