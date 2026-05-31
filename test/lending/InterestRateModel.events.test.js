const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("InterestRateModel", function () {
  it("emits both compatibility and detailed parameter update events", async function () {
    const InterestRateModel = await ethers.getContractFactory("InterestRateModel");
    const irm = await InterestRateModel.deploy(100, 200, 300, 400);
    await irm.waitForDeployment();

    const tx = await irm.updateParams(1000, 2000, 3000, 4000);
    const receipt = await tx.wait();

    const decodedLogs = receipt.logs
      .map((log) => {
        try {
          return irm.interface.parseLog(log);
        } catch {
          return null;
        }
      })
      .filter(Boolean);

    const compatibilityEvent = decodedLogs.find((item) => item.name === "RateParamsUpdated");
    expect(compatibilityEvent).to.not.equal(undefined);
    expect(compatibilityEvent.args.baseRate).to.equal(1000n);
    expect(compatibilityEvent.args.multiplier).to.equal(2000n);
    expect(compatibilityEvent.args.jumpMultiplier).to.equal(3000n);
    expect(compatibilityEvent.args.kink).to.equal(4000n);

    const detailedEvent = decodedLogs.find((item) => item.name === "RateParametersUpdated");
    expect(detailedEvent).to.not.equal(undefined);
    expect(detailedEvent.args.oldBaseRate).to.equal(100n);
    expect(detailedEvent.args.newBaseRate).to.equal(1000n);
    expect(detailedEvent.args.oldMultiplier).to.equal(200n);
    expect(detailedEvent.args.newMultiplier).to.equal(2000n);
    expect(detailedEvent.args.oldJumpMultiplier).to.equal(300n);
    expect(detailedEvent.args.newJumpMultiplier).to.equal(3000n);
    expect(detailedEvent.args.oldKink).to.equal(400n);
    expect(detailedEvent.args.newKink).to.equal(4000n);
  });

  it("returns all current parameters via getParameters()", async function () {
    const InterestRateModel = await ethers.getContractFactory("InterestRateModel");
    const irm = await InterestRateModel.deploy(11, 22, 33, 44);
    await irm.waitForDeployment();

    let params = await irm.getParameters();
    expect(params.baseRate).to.equal(11n);
    expect(params.multiplier).to.equal(22n);
    expect(params.jumpMultiplier).to.equal(33n);
    expect(params.kink).to.equal(44n);

    await irm.updateParams(111, 222, 333, 444);
    params = await irm.getParameters();
    expect(params.baseRate).to.equal(111n);
    expect(params.multiplier).to.equal(222n);
    expect(params.jumpMultiplier).to.equal(333n);
    expect(params.kink).to.equal(444n);
  });
});
