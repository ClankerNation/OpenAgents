const { expect } = require("chai");
const { ethers } = require("hardhat");

// @contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
// @platform full verbatim block: header of contracts/lending/InterestRateModel.sol
// @runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
//   shell=C:\Program Files\Git\bin\bash.exe
// @date 2026-11-04T19:20:00Z

const P = (n) => ethers.parseEther(String(n));

async function deploy() {
  const [admin, other] = await ethers.getSigners();
  const Model = await ethers.getContractFactory("InterestRateModel");
  const model = await Model.deploy(P("0.02"), P("0.1"), P("0.5"), P("0.8"));
  return { admin, other, model };
}

describe("InterestRateModel parameter events", function () {
  it("emits old and new values on a parameter change", async function () {
    const { model } = await deploy();
    await expect(model.updateParams(P("0.05"), P("0.2"), P("0.9"), P("0.7")))
      .to.emit(model, "RateParametersUpdated")
      .withArgs(P("0.02"), P("0.1"), P("0.5"), P("0.8"), P("0.05"), P("0.2"), P("0.9"), P("0.7"));
  });

  it("keeps emitting the plain confirmation event", async function () {
    const { model } = await deploy();
    await expect(model.updateParams(P("0.05"), P("0.2"), P("0.9"), P("0.7")))
      .to.emit(model, "RateParamsUpdated")
      .withArgs(P("0.05"), P("0.2"), P("0.9"), P("0.7"));
  });

  it("carries the previous values when only one field moves", async function () {
    const { model } = await deploy();
    await model.updateParams(P("0.02"), P("0.1"), P("0.5"), P("0.8"));
    await model.updateParams(P("0.03"), P("0.1"), P("0.5"), P("0.8"));

    const events = await model.queryFilter("RateParametersUpdated");
    const last = events[events.length - 1].args;
    expect(last.oldBaseRate).to.equal(P("0.02"));
    expect(last.newBaseRate).to.equal(P("0.03"));
    expect(last.oldMultiplier).to.equal(last.newMultiplier);
  });

  it("returns every parameter in one call", async function () {
    const { model } = await deploy();
    const params = await model.getParams();
    expect(params).to.deep.equal([P("0.02"), P("0.1"), P("0.5"), P("0.8")]);
  });

  it("getParams follows updates", async function () {
    const { model } = await deploy();
    await model.updateParams(P("0.07"), P("0.3"), P("1.1"), P("0.6"));
    expect(await model.getParams()).to.deep.equal([P("0.07"), P("0.3"), P("1.1"), P("0.6")]);
  });

  it("only the admin may change parameters", async function () {
    const { model, other } = await deploy();
    await expect(
      model.connect(other).updateParams(P("0.05"), P("0.2"), P("0.9"), P("0.7"))
    ).to.be.revertedWith("Not admin");
  });

  it("leaves the rate maths untouched", async function () {
    const { model } = await deploy();
    // 400/1000 utilization = 0.4 < kink 0.8 -> base + util*multiplier
    expect(await model.getBorrowRate(400, 1000)).to.equal(P("0.02") + (P("0.4") * P("0.1")) / P("1"));
    expect(await model.getUtilization(400, 1000)).to.equal(P("0.4"));
  });
});
