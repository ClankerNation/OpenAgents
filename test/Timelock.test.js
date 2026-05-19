const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Timelock", function () {
  let timelock;
  let admin, nonAdmin;

  const DELAY = 2 * 24 * 60 * 60; // 2 days
  const GRACE_PERIOD = 14 * 24 * 60 * 60; // 14 days

  beforeEach(async function () {
    [admin, nonAdmin] = await ethers.getSigners();
    const Timelock = await ethers.getContractFactory("Timelock");
    timelock = await Timelock.deploy(admin.address, DELAY);
    await timelock.deployed();
  });

  describe("constructor", function () {
    it("should initialize with correct admin and delay", async function () {
      expect(await timelock.admin()).to.equal(admin.address);
      expect(await timelock.delay()).to.equal(DELAY);
    });

    it("should reject delay of zero", async function () {
      const Timelock = await ethers.getContractFactory("Timelock");
      await expect(
        Timelock.deploy(admin.address, 0)
      ).to.be.revertedWith("Timelock: delay cannot be zero");
    });

    it("should reject delay exceeding max", async function () {
      const Timelock = await ethers.getContractFactory("Timelock");
      const MAX = 30 * 24 * 60 * 60;
      await expect(
        Timelock.deploy(admin.address, MAX + 1)
      ).to.be.revertedWith("Timelock: delay exceeds max");
    });
  });

  describe("setDelay", function () {
    it("should update delay when called by admin", async function () {
      const newDelay = 7 * 24 * 60 * 60; // 7 days
      await timelock.connect(admin).setDelay(newDelay);
      expect(await timelock.delay()).to.equal(newDelay);
    });

    it("should emit NewDelay event", async function () {
      const newDelay = 7 * 24 * 60 * 60;
      await expect(timelock.connect(admin).setDelay(newDelay))
        .to.emit(timelock, "NewDelay")
        .withArgs(newDelay);
    });

    it("should reject non-admin caller", async function () {
      await expect(
        timelock.connect(nonAdmin).setDelay(100)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });

    it("should reject delay of zero", async function () {
      await expect(
        timelock.connect(admin).setDelay(0)
      ).to.be.revertedWith("Timelock: delay cannot be zero");
    });

    it("should reject delay exceeding max", async function () {
      const MAX = 30 * 24 * 60 * 60;
      await expect(
        timelock.connect(admin).setDelay(MAX + 1)
      ).to.be.revertedWith("Timelock: delay exceeds max");
    });
  });

  describe("setPendingAdmin", function () {
    it("should set pending admin when called by admin", async function () {
      await timelock.connect(admin).setPendingAdmin(nonAdmin.address);
      expect(await timelock.pendingAdmin()).to.equal(nonAdmin.address);
    });

    it("should emit NewPendingAdmin event", async function () {
      await expect(timelock.connect(admin).setPendingAdmin(nonAdmin.address))
        .to.emit(timelock, "NewPendingAdmin")
        .withArgs(nonAdmin.address);
    });

    it("should reject non-admin caller", async function () {
      await expect(
        timelock.connect(nonAdmin).setPendingAdmin(nonAdmin.address)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });

    it("should reject zero address", async function () {
      await expect(
        timelock.connect(admin).setPendingAdmin(ethers.constants.AddressZero)
      ).to.be.revertedWith("Timelock: pending admin is zero address");
    });
  });

  describe("acceptAdmin", function () {
    it("should transfer admin to pending admin", async function () {
      await timelock.connect(admin).setPendingAdmin(nonAdmin.address);
      await timelock.connect(nonAdmin).acceptAdmin();
      expect(await timelock.admin()).to.equal(nonAdmin.address);
      expect(await timelock.pendingAdmin()).to.equal(ethers.constants.AddressZero);
    });

    it("should reject non-pending caller", async function () {
      await expect(
        timelock.connect(nonAdmin).acceptAdmin()
      ).to.be.revertedWith("Timelock: not pending admin");
    });
  });

  describe("queueTransaction", function () {
    const target = "0x0000000000000000000000000000000000000001";
    const value = 0;
    const data = "0x";

    it("should queue a transaction with valid eta", async function () {
      const latestBlock = await ethers.provider.getBlock("latest");
      const eta = latestBlock.timestamp + DELAY + 100;

      await expect(
        timelock.connect(admin).queueTransaction(target, value, data, eta)
      )
        .to.emit(timelock, "QueueTransaction");
    });

    it("should reject eta too early (less than block.timestamp + delay)", async function () {
      const latestBlock = await ethers.provider.getBlock("latest");
      const eta = latestBlock.timestamp + DELAY - 1;

      await expect(
        timelock.connect(admin).queueTransaction(target, value, data, eta)
      ).to.be.revertedWith("Timelock: eta too early");
    });

    it("should reject non-admin caller", async function () {
      const latestBlock = await ethers.provider.getBlock("latest");
      const eta = latestBlock.timestamp + DELAY + 100;

      await expect(
        timelock.connect(nonAdmin).queueTransaction(target, value, data, eta)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });
  });

  describe("executeTransaction", function () {
    const target = "0x0000000000000000000000000000000000000001";
    const value = 0;
    const data = "0x";

    async function queueValidTx() {
      const latestBlock = await ethers.provider.getBlock("latest");
      const eta = latestBlock.timestamp + DELAY + 100;
      await timelock.connect(admin).queueTransaction(target, value, data, eta);
      return eta;
    }

    it("should execute a queued transaction within the grace window", async function () {
      const eta = await queueValidTx();

      // Fast-forward past eta
      await ethers.provider.send("evm_setNextBlockTimestamp", [eta + 1]);
      await ethers.provider.send("evm_mine");

      await expect(
        timelock.connect(admin).executeTransaction(target, value, data, eta)
      )
        .to.emit(timelock, "ExecuteTransaction");
    });

    it("should revert with 'stale' after grace period", async function () {
      const eta = await queueValidTx();

      // Fast-forward past grace period
      await ethers.provider.send("evm_setNextBlockTimestamp", [eta + GRACE_PERIOD + 1]);
      await ethers.provider.send("evm_mine");

      await expect(
        timelock.connect(admin).executeTransaction(target, value, data, eta)
      ).to.be.revertedWith("Timelock: tx stale");
    });

    it("should revert with 'eta not reached' before eta", async function () {
      const eta = await queueValidTx();

      // Don't fast-forward — we're still before eta
      await expect(
        timelock.connect(admin).executeTransaction(target, value, data, eta)
      ).to.be.revertedWith("Timelock: eta not reached");
    });

    it("should revert if transaction not queued", async function () {
      const latestBlock = await ethers.provider.getBlock("latest");
      const eta = latestBlock.timestamp + 100;

      await expect(
        timelock.connect(admin).executeTransaction(target, value, data, eta)
      ).to.be.revertedWith("Timelock: tx not queued");
    });

    it("should reject non-admin caller", async function () {
      const eta = await queueValidTx();

      await ethers.provider.send("evm_setNextBlockTimestamp", [eta + 1]);
      await ethers.provider.send("evm_mine");

      await expect(
        timelock.connect(nonAdmin).executeTransaction(target, value, data, eta)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });

    it("should clear queued flag after execution", async function () {
      const eta = await queueValidTx();

      await ethers.provider.send("evm_setNextBlockTimestamp", [eta + 1]);
      await ethers.provider.send("evm_mine");

      const txHash = ethers.utils.keccak256(
        ethers.utils.defaultAbiCoder.encode(
          ["address", "uint256", "bytes", "uint256"],
          [target, value, data, eta]
        )
      );

      await timelock.connect(admin).executeTransaction(target, value, data, eta);
      expect(await timelock.queuedTransactions(txHash)).to.equal(false);
    });
  });

  describe("cancelTransaction", function () {
    const target = "0x0000000000000000000000000000000000000001";
    const value = 0;
    const data = "0x";

    async function queueValidTx() {
      const latestBlock = await ethers.provider.getBlock("latest");
      const eta = latestBlock.timestamp + DELAY + 100;
      await timelock.connect(admin).queueTransaction(target, value, data, eta);
      return eta;
    }

    it("should cancel a queued transaction", async function () {
      const eta = await queueValidTx();

      await expect(
        timelock.connect(admin).cancelTransaction(target, value, data, eta)
      )
        .to.emit(timelock, "CancelTransaction");
    });

    it("should clear queuedTransactions flag after cancel", async function () {
      const eta = await queueValidTx();

      const txHash = ethers.utils.keccak256(
        ethers.utils.defaultAbiCoder.encode(
          ["address", "uint256", "bytes", "uint256"],
          [target, value, data, eta]
        )
      );

      await timelock.connect(admin).cancelTransaction(target, value, data, eta);
      expect(await timelock.queuedTransactions(txHash)).to.equal(false);
    });

    it("should reject non-admin caller", async function () {
      const eta = await queueValidTx();

      await expect(
        timelock.connect(nonAdmin).cancelTransaction(target, value, data, eta)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });

    it("should reject cancellation of non-queued transaction", async function () {
      const latestBlock = await ethers.provider.getBlock("latest");
      const eta = latestBlock.timestamp + 100;

      await expect(
        timelock.connect(admin).cancelTransaction(target, value, data, eta)
      ).to.be.revertedWith("Timelock: tx not queued");
    });

    it("should prevent execution after cancel", async function () {
      const eta = await queueValidTx();

      // Cancel the transaction
      await timelock.connect(admin).cancelTransaction(target, value, data, eta);

      // Fast-forward past eta
      await ethers.provider.send("evm_setNextBlockTimestamp", [eta + 1]);
      await ethers.provider.send("evm_mine");

      // Execution should revert because tx is no longer queued
      await expect(
        timelock.connect(admin).executeTransaction(target, value, data, eta)
      ).to.be.revertedWith("Timelock: tx not queued");
    });
  });
});
