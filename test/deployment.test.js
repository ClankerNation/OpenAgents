const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("SDK DeployContract", function () {
  let deployer;

  before(async function () {
    [deployer] = await ethers.getSigners();
  });

  it("should deploy a contract with constructor arguments", async function () {
    const SimpleStorage = await ethers.getContractFactory("SimpleStorage");
    const bytecode = SimpleStorage.bytecode;
    const abi = SimpleStorage.interface.fragments;

    const factory = new ethers.ContractFactory(abi, bytecode, deployer);
    const contract = await factory.deploy(42);
    const receipt = await contract.deploymentTransaction().wait(1);

    expect(receipt.contractAddress).to.not.be.null;
    expect(receipt.status).to.equal(1);
    expect(receipt.gasUsed).to.be.gt(0);

    const value = await contract.retrieve();
    expect(value).to.equal(42);
  });

  it("should wait for configurable confirmations", async function () {
    const SimpleStorage = await ethers.getContractFactory("SimpleStorage");
    const factory = new ethers.ContractFactory(
      SimpleStorage.interface.fragments,
      SimpleStorage.bytecode,
      deployer
    );
    const contract = await factory.deploy(100);

    // Wait for 1 confirmation (default) - Hardhat mines instantly
    const receipt = await contract.deploymentTransaction().wait(1);

    expect(receipt.blockNumber).to.not.be.null;
    const confirmations = await receipt.confirmations();
    expect(confirmations).to.be.gte(1);
  });

  it("should return complete deployment receipt metadata", async function () {
    const SimpleStorage = await ethers.getContractFactory("SimpleStorage");
    const factory = new ethers.ContractFactory(
      SimpleStorage.interface.fragments,
      SimpleStorage.bytecode,
      deployer
    );
    const contract = await factory.deploy(200);
    const receipt = await contract.deploymentTransaction().wait(1);

    // All required metadata fields present
    expect(receipt.contractAddress).to.be.a("string");
    expect(receipt.hash).to.be.a("string");
    expect(typeof receipt.gasUsed).to.equal("bigint");
    expect(receipt.blockNumber).to.be.a("number");
    expect(receipt.blockHash).to.be.a("string");
    expect(receipt.status).to.equal(1);
  });

  it("should correctly encode constructor arguments", async function () {
    const SimpleStorage = await ethers.getContractFactory("SimpleStorage");
    const factory = new ethers.ContractFactory(
      SimpleStorage.interface.fragments,
      SimpleStorage.bytecode,
      deployer
    );
    const initialValue = 999;
    const contract = await factory.deploy(initialValue);
    await contract.deploymentTransaction().wait(1);

    const value = await contract.retrieve();
    expect(value).to.equal(initialValue);
  });
});
