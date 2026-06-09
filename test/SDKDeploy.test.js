const { expect } = require("chai");
const { ethers } = require("hardhat");

// We test the deployContract logic directly using ethers factory pattern
// since the SDK uses ethers.ContractFactory internally

describe("OpenAgentsSDK - deployContract equivalent", function () {
  let deployer;

  before(async function () {
    [deployer] = await ethers.getSigners();
  });

  it("should deploy a contract with constructor args and return address", async function () {
    const TestDeploy = await ethers.getContractFactory("TestDeploy");
    const contract = await TestDeploy.deploy("DeployedAgent", 99);
    await contract.waitForDeployment();

    const deployTx = contract.deploymentTransaction();
    const receipt = await deployTx.wait();

    expect(contract.target).to.match(/^0x[0-9a-fA-F]{40}$/);
    expect(deployTx.hash).to.match(/^0x[0-9a-fA-F]{64}$/);
    expect(receipt.gasUsed).to.be.gt(0n);
    expect(receipt.blockNumber).to.be.gt(0);
    expect(receipt.status).to.equal(1);

    // Verify constructor args were correctly encoded
    expect(await contract.name()).to.equal("DeployedAgent");
    expect(await contract.value()).to.equal(99n);
  });

  it("should deploy with custom confirmation depth", async function () {
    const TestDeploy = await ethers.getContractFactory("TestDeploy");
    const contract = await TestDeploy.deploy("ConfirmTest", 1);
    await contract.waitForDeployment();

    const deployTx = contract.deploymentTransaction();
    const receipt = await deployTx.wait(1);

    expect(receipt.status).to.equal(1);
    expect(await contract.name()).to.equal("ConfirmTest");
  });

  it("should include all receipt metadata", async function () {
    const TestDeploy = await ethers.getContractFactory("TestDeploy");
    const contract = await TestDeploy.deploy("MetadataTest", 7);
    await contract.waitForDeployment();

    const deployTx = contract.deploymentTransaction();
    const receipt = await deployTx.wait();

    expect(receipt).to.have.property("blockHash");
    expect(receipt).to.have.property("contractAddress");
    expect(receipt.from).to.equal(deployer.address);
    expect(receipt.status).to.equal(1);
    expect(receipt.gasUsed).to.be.gt(0n);
  });

  it("should accept empty constructor args", async function () {
    const TestNoArgs = await ethers.getContractFactory("TestNoArgs");
    const contract = await TestNoArgs.deploy();
    await contract.waitForDeployment();

    expect(contract.target).to.match(/^0x[0-9a-fA-F]{40}$/);
    expect(await contract.value()).to.equal(42n);
  });
});
