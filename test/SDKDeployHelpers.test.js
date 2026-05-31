const { expect } = require("chai");
const fs = require("fs");
const path = require("path");

describe("OpenAgentsSDK deploy helper surface", function () {
  const sdkPath = path.join(__dirname, "..", "sdk", "src", "index.ts");
  const source = fs.readFileSync(sdkPath, "utf8");

  it("includes deployContract helper", function () {
    expect(source).to.include("async deployContract(");
    expect(source).to.include("new ethers.ContractFactory");
  });

  it("waits for deployment confirmations", function () {
    expect(source).to.include("deploymentTx.wait(confirmations)");
  });

  it("stores deployment receipt with address, txHash and gasUsed", function () {
    expect(source).to.include("address");
    expect(source).to.include("txHash");
    expect(source).to.include("gasUsed");
    expect(source).to.include("getLastDeploymentReceipt()");
  });
});
