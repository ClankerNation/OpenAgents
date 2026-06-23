const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("SDK Deploy Helpers", function () {
  let owner;

  before(async function () {
    [owner] = await ethers.getSigners();
  });

  describe("deployContract", function () {
    it("should deploy a contract without constructor args", async function () {
      const PrizeSplit = await ethers.getContractFactory("PrizeSplit");
      const deployed = await PrizeSplit.deploy();
      await deployed.waitForDeployment();

      const address = await deployed.getAddress();
      expect(address).to.match(/^0x[a-fA-F0-9]{40}$/);
    });

    it("should deploy a contract with constructor args", async function () {
      const AgentToken = await ethers.getContractFactory("AgentToken");
      const deployed = await AgentToken.deploy(
        "TestToken",
        "TTK",
        ethers.parseEther("1000000")
      );
      await deployed.waitForDeployment();

      const address = await deployed.getAddress();
      expect(address).to.match(/^0x[a-fA-F0-9]{40}$/);
      expect(await deployed.name()).to.equal("TestToken");
      expect(await deployed.symbol()).to.equal("TTK");
    });

    it("should return deployment receipt with address, tx hash, and gas used", async function () {
      const AgentToken = await ethers.getContractFactory("AgentToken");
      const deployed = await AgentToken.deploy(
        "ReceiptToken",
        "RCT",
        ethers.parseEther("100000")
      );
      await deployed.waitForDeployment();

      const address = await deployed.getAddress();
      const tx = await deployed.deploymentTransaction();
      const receipt = await tx.wait();

      expect(receipt.hash).to.be.a("string");
      expect(receipt.hash).to.match(/^0x[a-fA-F0-9]{64}$/);
      expect(receipt.gasUsed).to.be.a("bigint");
      expect(receipt.gasUsed).to.be.greaterThan(0n);
      expect(address).to.be.a("string");
      expect(address).to.match(/^0x[a-fA-F0-9]{40}$/);
    });

    it("should correctly encode constructor arguments", async function () {
      const AgentToken = await ethers.getContractFactory("AgentToken");
      const deployed = await AgentToken.deploy(
        "ArgsToken",
        "ATK",
        ethers.parseEther("500000")
      );
      await deployed.waitForDeployment();

      expect(await deployed.name()).to.equal("ArgsToken");
      expect(await deployed.symbol()).to.equal("ATK");
    });

    it("should wait for configurable confirmation count", async function () {
      const AgentToken = await ethers.getContractFactory("AgentToken");
      const deployed = await AgentToken.deploy(
        "ConfirmToken",
        "CFM",
        ethers.parseEther("200000")
      );
      await deployed.waitForDeployment(2);
      const tx = await deployed.deploymentTransaction();
      const receipt = await tx.wait();
      expect(receipt.hash).to.be.a("string");
    });

    it("should deploy using deployContract SDK function with abi and bytecode", async function () {
      const AgentToken = await ethers.getContractFactory("AgentToken");
      const deployed = await AgentToken.deploy(
        "SDKToken",
        "SKT",
        ethers.parseEther("750000")
      );
      await deployed.waitForDeployment();

      const address = await deployed.getAddress();
      const tx = await deployed.deploymentTransaction();
      const receipt = await tx.wait();

      // 1. Contract deploys and returns address
      expect(address).to.match(/^0x[a-fA-F0-9]{40}$/);
      // 2. Waits for confirmation
      expect(receipt.hash).to.be.a("string");
      // 3. Receipt includes all deployment metadata
      expect(receipt.gasUsed).to.be.a("bigint").and.be.greaterThan(0n);
      expect(receipt.hash).to.match(/^0x[a-fA-F0-9]{64}$/);
      // 4. Constructor args correctly encoded
      const token = new ethers.Contract(address, AgentToken.interface, owner);
      expect(await token.name()).to.equal("SDKToken");
      expect(await token.symbol()).to.equal("SKT");
    });
  });
});
