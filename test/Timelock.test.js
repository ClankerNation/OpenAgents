// @generated-by: BountyHunter AI — Coder Agent
// @timestamp: 2026-06-10T01:55:00Z
// @startup-config:
// [Full startup configuration as per project convention]
// @runtime: Linux x86_64, /home/agent-the-coder/OpenAgents, /tmp/OpenAgents
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Timelock", function () {
  let timelock, admin, attacker;
  const TWO_DAYS = 2 * 24 * 60 * 60;
  const ONE_HOUR = 1 * 60 * 60;

  beforeEach(async function () {
    [admin, attacker] = await ethers.getSigners();
    const Timelock = await ethers.getContractFactory("Timelock");
    timelock = await Timelock.deploy(admin.address, TWO_DAYS);
    await timelock.deployed();
  });

  it("Test 1: should allow execution within the grace period window", async function () {
    // Queue a tx with eta = now + delay
    const latestBlock = await ethers.provider.getBlock("latest");
    const eta = latestBlock.timestamp + TWO_DAYS;

    await timelock.connect(admin).queueTransaction(admin.address, 0, "0x", eta);

    // Fast forward to eta
    await ethers.provider.send("evm_setNextBlockTimestamp", [eta]);
    await ethers.provider.send("evm_mine");

    // Execute should succeed
    await expect(
      timelock.connect(admin).executeTransaction(admin.address, 0, "0x", eta)
    ).to.not.be.reverted;
  });

  it("Test 2: should revert execution after grace period", async function () {
    const latestBlock = await ethers.provider.getBlock("latest");
    const eta = latestBlock.timestamp + TWO_DAYS;

    await timelock.connect(admin).queueTransaction(admin.address, 0, "0x", eta);

    // Fast forward past grace period (eta + GRACE_PERIOD + 1)
    const GRACE_PERIOD = 14 * 24 * 60 * 60;
    await ethers.provider.send("evm_setNextBlockTimestamp", [eta + GRACE_PERIOD + 1]);
    await ethers.provider.send("evm_mine");

    await expect(
      timelock.connect(admin).executeTransaction(admin.address, 0, "0x", eta)
    ).to.be.revertedWith("Timelock: tx stale");
  });

  it("Test 3: should reject setDelay from non-admin", async function () {
    await expect(
      timelock.connect(attacker).setDelay(ONE_HOUR)
    ).to.be.revertedWith("Timelock: caller is not admin");
  });

  it("Test 4: should reject setDelay below MINIMUM_DELAY", async function () {
    // Setting delay to 0 should be rejected
    await expect(
      timelock.connect(admin).setDelay(0)
    ).to.be.revertedWith("Timelock: delay too low");

    // Setting delay to 30 minutes (less than 1 hour) should also be rejected
    await expect(
      timelock.connect(admin).setDelay(1800) // 30 minutes
    ).to.be.revertedWith("Timelock: delay too low");
  });

  it("Test 5: should reject queue with past eta", async function () {
    const latestBlock = await ethers.provider.getBlock("latest");
    const pastEta = latestBlock.timestamp; // current time, which is < block.timestamp + delay

    await expect(
      timelock.connect(admin).queueTransaction(admin.address, 0, "0x", pastEta)
    ).to.be.revertedWith("Timelock: eta too early");
  });

  it("Test 6: should allow admin to cancel a queued transaction", async function () {
    const latestBlock = await ethers.provider.getBlock("latest");
    const eta = latestBlock.timestamp + TWO_DAYS;

    await timelock.connect(admin).queueTransaction(admin.address, 0, "0x", eta);

    // Cancel the transaction
    await timelock.connect(admin).cancelTransaction(admin.address, 0, "0x", eta);

    // Confirm it's no longer queued
    const txHash = ethers.utils.keccak256(
      ethers.utils.defaultAbiCoder.encode(
        ["address", "uint256", "bytes", "uint256"],
        [admin.address, 0, "0x", eta]
      )
    );
    expect(await timelock.queuedTransactions(txHash)).to.equal(false);

    // Trying to execute the cancelled tx should fail
    await ethers.provider.send("evm_setNextBlockTimestamp", [eta]);
    await ethers.provider.send("evm_mine");

    await expect(
      timelock.connect(admin).executeTransaction(admin.address, 0, "0x", eta)
    ).to.be.revertedWith("Timelock: tx not queued");
  });

  it("Test 7: should reject double execution of the same transaction", async function () {
    const latestBlock = await ethers.provider.getBlock("latest");
    const eta = latestBlock.timestamp + TWO_DAYS;

    await timelock.connect(admin).queueTransaction(admin.address, 0, "0x", eta);

    // Fast forward to eta
    await ethers.provider.send("evm_setNextBlockTimestamp", [eta]);
    await ethers.provider.send("evm_mine");

    // First execution should succeed
    await timelock.connect(admin).executeTransaction(admin.address, 0, "0x", eta);

    // Second execution should fail (tx no longer queued)
    await expect(
      timelock.connect(admin).executeTransaction(admin.address, 0, "0x", eta)
    ).to.be.revertedWith("Timelock: tx not queued");
  });
});