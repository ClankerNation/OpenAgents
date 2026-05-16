const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("Timelock", function () {
  let timelock;
  let admin, other;
  const DELAY = 2 * 24 * 60 * 60; // 2 days
  const GRACE_PERIOD = 14 * 24 * 60 * 60; // 14 days
  const TARGET = "0x0000000000000000000000000000000000000001"; // burn address as test target

  beforeEach(async function () {
    [admin, other] = await ethers.getSigners();
    const Timelock = await ethers.getContractFactory("Timelock");
    timelock = await Timelock.deploy(admin.address, DELAY);
    await timelock.waitForDeployment();
  });

  // ===== Constructor =====
  describe("constructor", function () {
    it("should set admin and delay", async function () {
      expect(await timelock.admin()).to.equal(admin.address);
      expect(await timelock.delay()).to.equal(DELAY);
    });

    it("should revert if delay exceeds MAXIMUM_DELAY", async function () {
      const MAX_DELAY = 30 * 24 * 60 * 60;
      const Timelock = await ethers.getContractFactory("Timelock");
      await expect(
        Timelock.deploy(admin.address, MAX_DELAY + 1)
      ).to.be.revertedWith("Timelock: delay exceeds max");
    });
  });

  // ===== setDelay (fixed: onlyAdmin + minimum delay) =====
  describe("setDelay", function () {
    it("should allow admin to set a valid delay", async function () {
      const newDelay = 7 * 24 * 60 * 60; // 7 days
      await expect(timelock.connect(admin).setDelay(newDelay))
        .to.emit(timelock, "NewDelay")
        .withArgs(newDelay);
      expect(await timelock.delay()).to.equal(newDelay);
    });

    it("should revert when non-admin tries to set delay", async function () {
      await expect(
        timelock.connect(other).setDelay(5 * 24 * 60 * 60)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });

    it("should revert when delay is 0", async function () {
      await expect(
        timelock.connect(admin).setDelay(0)
      ).to.be.revertedWith("Timelock: delay below minimum");
    });

    it("should revert when delay is below MINIMUM_DELAY (1 hour)", async function () {
      await expect(
        timelock.connect(admin).setDelay(1800) // 30 min < 1 hour
      ).to.be.revertedWith("Timelock: delay below minimum");
    });

    it("should revert when delay exceeds MAXIMUM_DELAY", async function () {
      const tooBig = 31 * 24 * 60 * 60;
      await expect(
        timelock.connect(admin).setDelay(tooBig)
      ).to.be.revertedWith("Timelock: delay exceeds max");
    });

    it("should allow setDelay at exactly MINIMUM_DELAY", async function () {
      const oneHour = 60 * 60;
      await expect(timelock.connect(admin).setDelay(oneHour))
        .to.emit(timelock, "NewDelay")
        .withArgs(oneHour);
    });
  });

  // ===== queueTransaction (fixed: eta validation) =====
  describe("queueTransaction", function () {
    const emptyData = "0x";

    it("should queue a transaction with valid eta", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + DELAY + 3600; // delay + 1 hour buffer

      await expect(
        timelock.connect(admin).queueTransaction(TARGET, 0, emptyData, eta)
      )
        .to.emit(timelock, "QueueTransaction");

      const txHash = ethers.keccak256(
        ethers.AbiCoder.defaultAbiCoder().encode(
          ["address", "uint256", "bytes", "uint256"],
          [TARGET, 0, emptyData, eta]
        )
      );
      expect(await timelock.queuedTransactions(txHash)).to.equal(true);
    });

    it("should revert when eta is too soon (past)", async function () {
      const now = (await ethers.provider.getBlock("latest")).timestamp;
      const pastEta = now - 3600; // in the past

      await expect(
        timelock.connect(admin).queueTransaction(TARGET, 0, emptyData, pastEta)
      ).to.be.revertedWith("Timelock: eta too soon");
    });

    it("should revert when eta is before block.timestamp + delay", async function () {
      const now = (await ethers.provider.getBlock("latest")).timestamp;
      const tooSoonEta = now + 3600; // 1 hour from now, but delay is 2 days

      await expect(
        timelock.connect(admin).queueTransaction(TARGET, 0, emptyData, tooSoonEta)
      ).to.be.revertedWith("Timelock: eta too soon");
    });

    it("should revert when non-admin tries to queue", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + DELAY + 3600;

      await expect(
        timelock.connect(other).queueTransaction(TARGET, 0, emptyData, eta)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });
  });

  // ===== executeTransaction — grace period behavior =====
  describe("executeTransaction", function () {
    const emptyData = "0x";
    let eta;

    beforeEach(async function () {
      const block = await ethers.provider.getBlock("latest");
      eta = block.timestamp + DELAY + 3600;
      await timelock.connect(admin).queueTransaction(TARGET, 0, emptyData, eta);
    });

    it("should execute within grace window", async function () {
      // Advance time to exactly eta
      await time.increaseTo(eta);

      await expect(
        timelock.connect(admin).executeTransaction(TARGET, 0, emptyData, eta)
      ).to.emit(timelock, "ExecuteTransaction");
    });

    it("should revert when eta has not been reached", async function () {
      await expect(
        timelock.connect(admin).executeTransaction(TARGET, 0, emptyData, eta)
      ).to.be.revertedWith("Timelock: eta not reached");
    });

    it("should revert after grace period expires (stale)", async function () {
      // Advance past eta + GRACE_PERIOD
      await time.increaseTo(eta + GRACE_PERIOD + 1);

      await expect(
        timelock.connect(admin).executeTransaction(TARGET, 0, emptyData, eta)
      ).to.be.revertedWith("Timelock: tx stale");
    });

    it("should revert for non-queued transaction", async function () {
      const otherEta = eta + 100000;
      await expect(
        timelock.connect(admin).executeTransaction(TARGET, 0, emptyData, otherEta)
      ).to.be.revertedWith("Timelock: tx not queued");
    });

    it("should revert when non-admin tries to execute", async function () {
      await time.increaseTo(eta);
      await expect(
        timelock.connect(other).executeTransaction(TARGET, 0, emptyData, eta)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });
  });

  // ===== cancelTransaction =====
  describe("cancelTransaction", function () {
    const emptyData = "0x";
    let eta, txHash;

    beforeEach(async function () {
      const block = await ethers.provider.getBlock("latest");
      eta = block.timestamp + DELAY + 3600;
      await timelock.connect(admin).queueTransaction(TARGET, 0, emptyData, eta);

      txHash = ethers.keccak256(
        ethers.AbiCoder.defaultAbiCoder().encode(
          ["address", "uint256", "bytes", "uint256"],
          [TARGET, 0, emptyData, eta]
        )
      );
    });

    it("should allow admin to cancel a queued transaction", async function () {
      expect(await timelock.queuedTransactions(txHash)).to.equal(true);

      await expect(
        timelock.connect(admin).cancelTransaction(TARGET, 0, emptyData, eta)
      )
        .to.emit(timelock, "CancelTransaction")
        .withArgs(txHash, TARGET, 0, emptyData, eta);

      expect(await timelock.queuedTransactions(txHash)).to.equal(false);
    });

    it("should prevent execution after cancel", async function () {
      await timelock.connect(admin).cancelTransaction(TARGET, 0, emptyData, eta);
      await time.increaseTo(eta);

      await expect(
        timelock.connect(admin).executeTransaction(TARGET, 0, emptyData, eta)
      ).to.be.revertedWith("Timelock: tx not queued");
    });

    it("should revert when non-admin tries to cancel", async function () {
      await expect(
        timelock.connect(other).cancelTransaction(TARGET, 0, emptyData, eta)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });
  });

  // ===== admin transfer =====
  describe("admin transfer", function () {
    it("should allow admin to set pending admin", async function () {
      await timelock.connect(admin).setPendingAdmin(other.address);
      expect(await timelock.pendingAdmin()).to.equal(other.address);
    });

    it("should allow pending admin to accept", async function () {
      await timelock.connect(admin).setPendingAdmin(other.address);
      await timelock.connect(other).acceptAdmin();
      expect(await timelock.admin()).to.equal(other.address);
    });

    it("should clear pending admin after acceptance", async function () {
      await timelock.connect(admin).setPendingAdmin(other.address);
      await timelock.connect(other).acceptAdmin();
      expect(await timelock.pendingAdmin()).to.equal(ethers.ZeroAddress);
    });
  });
});
