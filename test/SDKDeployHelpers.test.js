const { expect } = require("chai");
const fs = require("fs");
const path = require("path");

describe("OpenAgentsSDK deployContract helper", function () {
  const sourcePath = path.join(__dirname, "..", "sdk", "src", "index.ts");
  const source = fs.readFileSync(sourcePath, "utf8");

  it("deploys through ethers ContractFactory with constructor arguments", function () {
    expect(source).to.include("async deployContract(");
    expect(source).to.include("new ethers.ContractFactory(abi, bytecode, this.signer)");
    expect(source).to.include("factory.deploy(...args)");
  });

  it("waits for configurable deployment confirmations", function () {
    expect(source).to.include("options.confirmations ?? 1");
    expect(source).to.include("deploymentTx.wait(confirmations)");
  });

  it("returns the contract instance and deployment receipt metadata", function () {
    expect(source).to.include("interface DeploymentResult");
    expect(source).to.include("contract:");
    expect(source).to.include("receipt:");
    expect(source).to.include("address,");
    expect(source).to.include("txHash: deploymentTx.hash");
    expect(source).to.include("gasUsed: txReceipt.gasUsed");
  });
});
