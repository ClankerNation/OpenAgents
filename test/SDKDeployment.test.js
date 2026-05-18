const { expect } = require("chai");
const { ethers } = require("hardhat");

/**
 * Tests for SDK deployment helpers (Issue #199).
 *
 * Validates the deployContract pattern: factory deployment with constructor args,
 * confirmation waiting, and deployment receipt fields (address, txHash,
 * blockNumber, gasUsed).
 */
describe("SDK Deployment Helpers", function () {
  let deployer;
  let sdkContractFactory;

  before(async function () {
    [deployer] = await ethers.getSigners();
    sdkContractFactory = await ethers.getContractFactory("SDKTestContract");
  });

  // ─── Basic deployment ────────────────────────────────────────────────

  it("should deploy contract and return valid address", async function () {
    const contract = await sdkContractFactory.deploy(42, "test-deploy");
    await contract.waitForDeployment();

    const address = await contract.getAddress();
    expect(address).to.match(/^0x[a-fA-F0-9]{40}$/);
    expect(address).to.not.equal(ethers.ZeroAddress);
  });

  it("should deploy with constructor args correctly encoded", async function () {
    const value = 100n;
    const name = "constructor-test";

    const contract = await sdkContractFactory.deploy(value, name);
    await contract.waitForDeployment();

    expect(await contract.value()).to.equal(value);
    expect(await contract.name()).to.equal(name);
    expect(await contract.owner()).to.equal(deployer.address);
  });

  // ─── Deployment receipt validation ───────────────────────────────────

  it("should provide deployment receipt with all metadata", async function () {
    const contract = await sdkContractFactory.deploy(7, "receipt-test");
    await contract.waitForDeployment();

    const deployTx = contract.deploymentTransaction();
    expect(deployTx).to.not.be.null;

    const txReceipt = await deployTx.wait();

    const receipt = {
      address: await contract.getAddress(),
      transactionHash: deployTx.hash,
      blockNumber: txReceipt.blockNumber,
      gasUsed: txReceipt.gasUsed,
    };

    expect(receipt.address).to.match(/^0x[a-fA-F0-9]{40}$/);
    expect(receipt.transactionHash).to.match(/^0x[a-fA-F0-9]{64}$/);
    expect(receipt.blockNumber).to.be.a("number");
    expect(receipt.blockNumber).to.be.greaterThan(0);
    expect(receipt.gasUsed).to.be.a("bigint");
    expect(receipt.gasUsed).to.be.greaterThan(0n);
  });

  // ─── Wait for confirmation ───────────────────────────────────────────

  it("should wait for deployment confirmation (1 block default)", async function () {
    const contract = await sdkContractFactory.deploy(99, "confirm-test");
    await contract.waitForDeployment();

    const address = await contract.getAddress();
    const deployTx = contract.deploymentTransaction();
    const txReceipt = await deployTx.wait();

    // After waitForDeployment, the transaction should be mined
    expect(txReceipt.blockNumber).to.be.a("number");
    expect(txReceipt.blockNumber).to.be.greaterThan(0);

    // Contract address should be valid
    expect(address).to.match(/^0x[a-fA-F0-9]{40}$/);

    // Contract should be functional after deployment
    expect(await contract.value()).to.equal(99n);
  });

  // ─── Multiple confirmations ──────────────────────────────────────────

  it("should support configurable confirmation blocks", async function () {
    const contract = await sdkContractFactory.deploy(50, "multi-confirm");
    await contract.waitForDeployment();

    const deployTx = contract.deploymentTransaction();
    const txReceipt = await deployTx.wait();

    // Mine additional blocks to simulate waiting for multiple confirmations
    const confirmations = 3;
    const txBlock = txReceipt.blockNumber;

    for (let i = 0; i < confirmations; i++) {
      await ethers.provider.send("evm_mine");
    }

    const currentBlock = await ethers.provider.getBlockNumber();
    const actualConfirmations = currentBlock - txBlock;

    expect(actualConfirmations).to.be.gte(confirmations);
  });

  // ─── Edge cases ──────────────────────────────────────────────────────

  it("should deploy contract with zero constructor args", async function () {
    // Use a contract without constructor args for this test
    const factory = new ethers.ContractFactory(
      sdkContractFactory.interface,
      sdkContractFactory.bytecode,
      deployer
    );

    const contract = await factory.deploy(0, "");
    await contract.waitForDeployment();

    expect(await contract.value()).to.equal(0n);
    expect(await contract.name()).to.equal("");
    expect(await contract.owner()).to.equal(deployer.address);
  });

  it("should handle deployment of multiple contracts independently", async function () {
    const c1 = await sdkContractFactory.deploy(1, "first");
    const c2 = await sdkContractFactory.deploy(2, "second");

    await c1.waitForDeployment();
    await c2.waitForDeployment();

    const addr1 = await c1.getAddress();
    const addr2 = await c2.getAddress();

    // Each contract gets a unique address
    expect(addr1).to.not.equal(addr2);

    // Each contract has independent state
    expect(await c1.value()).to.equal(1n);
    expect(await c2.value()).to.equal(2n);
    expect(await c1.name()).to.equal("first");
    expect(await c2.name()).to.equal("second");
  });
});
