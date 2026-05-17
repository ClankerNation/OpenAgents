const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Timelock", function () {
  let timelock;
  let admin, other;
  const MIN_DELAY = 86400; // 1 day
  const GRACE_PERIOD = 14 * 86400;
  const MAX_DELAY = 30 * 86400;

  beforeEach(async function () {
    [admin, other] = await ethers.getSigners();
    const Timelock = await ethers.getContractFactory("Timelock");
    timelock = await Timelock.deploy(admin.address, MIN_DELAY);
    await timelock.deployed();
  });

  // ===== Constructor =====
  describe("constructor", function () {
    it("should set admin and delay", async function () {
      expect(await timelock.admin()).to.equal(admin.address);
      expect(await timelock.delay()).to.equal(MIN_DELAY);
    });

    it("should reject delay exceeding maximum", async function () {
      const Timelock = await ethers.getContractFactory("Timelock");
      await expect(
        Timelock.deploy(admin.address, MAX_DELAY + 1)
      ).to.be.revertedWith("Timelock: delay exceeds max");
    });

    it("should reject delay below minimum", async function () {
      const Timelock = await ethers.getContractFactory("Timelock");
      await expect(
        Timelock.deploy(admin.address, MIN_DELAY - 1)
      ).to.be.revertedWith("Timelock: delay below min");
    });
  });

  // ===== setDelay =====
  describe("setDelay", function () {
    it("should allow admin to set a valid delay", async function () {
      const newDelay = 7 * 86400; // 7 days
      await timelock.connect(admin).setDelay(newDelay);
      expect(await timelock.delay()).to.equal(newDelay);
    });

    it("should reject non-admin callers", async function () {
      await expect(
        timelock.connect(other).setDelay(7 * 86400)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });

    it("should reject delay below minimum", async function () {
      await expect(
        timelock.connect(admin).setDelay(MIN_DELAY - 1)
      ).to.be.revertedWith("Timelock: delay below min");
    });

    it("should reject delay above maximum", async function () {
      await expect(
        timelock.connect(admin).setDelay(MAX_DELAY + 1)
      ).to.be.revertedWith("Timelock: delay exceeds max");
    });

    it("should emit NewDelay event", async function () {
      const newDelay = 3 * 86400;
      await expect(timelock.connect(admin).setDelay(newDelay))
        .to.emit(timelock, "NewDelay")
        .withArgs(newDelay);
    });
  });

  // ===== Admin Transfer =====
  describe("admin transfer", function () {
    it("should allow admin to set pending admin", async function () {
      await timelock.connect(admin).setPendingAdmin(other.address);
      expect(await timelock.pendingAdmin()).to.equal(other.address);
    });

    it("should allow pending admin to accept role", async function () {
      await timelock.connect(admin).setPendingAdmin(other.address);
      await timelock.connect(other).acceptAdmin();
      expect(await timelock.admin()).to.equal(other.address);
    });

    it("should reject non-pending admin accepting role", async function () {
      await expect(
        timelock.connect(other).acceptAdmin()
      ).to.be.revertedWith("Timelock: not pending admin");
    });

    it("should clear pending admin after acceptance", async function () {
      await timelock.connect(admin).setPendingAdmin(other.address);
      await timelock.connect(other).acceptAdmin();
      expect(await timelock.pendingAdmin()).to.equal(
        "0x0000000000000000000000000000000000000000"
      );
    });
  });

  // ===== Queue Transaction =====
  describe("queueTransaction", function () {
    it("should queue a transaction with valid eta", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await timelock.connect(admin).queueTransaction(
        other.address, 0, "0x", eta
      );
      const txHash = ethers.utils.keccak256(
        ethers.utils.defaultAbiCoder.encode(
          ["address", "uint256", "bytes", "uint256"],
          [other.address, 0, "0x", eta]
        )
      );
      expect(await timelock.queuedTransactions(txHash)).to.be.true;
    });

    it("should reject eta too soon (before block.timestamp + delay)", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY - 1;
      await expect(
        timelock.connect(admin).queueTransaction(
          other.address, 0, "0x", eta
        )
      ).to.be.revertedWith("Timelock: eta too soon");
    });

    it("should reject eta equal to block.timestamp", async function () {
      const block = await ethers.provider.getBlock("latest");
      await expect(
        timelock.connect(admin).queueTransaction(
          other.address, 0, "0x", block.timestamp
        )
      ).to.be.revertedWith("Timelock: eta too soon");
    });

    it("should reject non-admin callers", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await expect(
        timelock.connect(other).queueTransaction(
          other.address, 0, "0x", eta
        )
      ).to.be.revertedWith("Timelock: caller is not admin");
    });

    it("should emit QueueTransaction event", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      const txHash = ethers.utils.keccak256(
        ethers.utils.defaultAbiCoder.encode(
          ["address", "uint256", "bytes", "uint256"],
          [other.address, 0, "0x", eta]
        )
      );
      await expect(
        timelock.connect(admin).queueTransaction(other.address, 0, "0x", eta)
      )
        .to.emit(timelock, "QueueTransaction")
        .withArgs(txHash, other.address, 0, "0x", eta);
    });
  });

  // ===== Execute Transaction =====
  describe("executeTransaction", function () {
    it("should execute within the execution window", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await timelock.connect(admin).queueTransaction(
        other.address, 0, "0x", eta
      );
      // Fast-forward to eta
      await ethers.provider.send("evm_setNextBlockTimestamp", [eta]);
      await ethers.provider.send("evm_mine");
      await timelock.connect(admin).executeTransaction(
        other.address, 0, "0x", eta
      );
      const txHash = ethers.utils.keccak256(
        ethers.utils.defaultAbiCoder.encode(
          ["address", "uint256", "bytes", "uint256"],
          [other.address, 0, "0x", eta]
        )
      );
      expect(await timelock.queuedTransactions(txHash)).to.be.false;
    });

    it("should reject execution before eta", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await timelock.connect(admin).queueTransaction(
        other.address, 0, "0x", eta
      );
      await expect(
        timelock.connect(admin).executeTransaction(
          other.address, 0, "0x", eta
        )
      ).to.be.revertedWith("Timelock: eta not reached");
    });

    it("should reject stale transactions (after GRACE_PERIOD)", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await timelock.connect(admin).queueTransaction(
        other.address, 0, "0x", eta
      );
      // Fast-forward past grace period
      const staleTime = eta + GRACE_PERIOD + 1;
      await ethers.provider.send("evm_setNextBlockTimestamp", [staleTime]);
      await ethers.provider.send("evm_mine");
      await expect(
        timelock.connect(admin).executeTransaction(
          other.address, 0, "0x", eta
        )
      ).to.be.revertedWith("Timelock: tx stale");
    });

    it("should reject unqueued transactions", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await ethers.provider.send("evm_setNextBlockTimestamp", [eta]);
      await ethers.provider.send("evm_mine");
      await expect(
        timelock.connect(admin).executeTransaction(
          other.address, 0, "0x", eta
        )
      ).to.be.revertedWith("Timelock: tx not queued");
    });

    it("should execute exactly at eta boundary", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await timelock.connect(admin).queueTransaction(
        other.address, 0, "0x", eta
      );
      await ethers.provider.send("evm_setNextBlockTimestamp", [eta]);
      await ethers.provider.send("evm_mine");
      await expect(
        timelock.connect(admin).executeTransaction(other.address, 0, "0x", eta)
      ).to.not.be.reverted;
    });

    it("should execute exactly at grace period boundary", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await timelock.connect(admin).queueTransaction(
        other.address, 0, "0x", eta
      );
      const graceDeadline = eta + GRACE_PERIOD;
      await ethers.provider.send("evm_setNextBlockTimestamp", [graceDeadline]);
      await ethers.provider.send("evm_mine");
      await expect(
        timelock.connect(admin).executeTransaction(other.address, 0, "0x", eta)
      ).to.not.be.reverted;
    });

    it("should prevent double execution", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await timelock.connect(admin).queueTransaction(
        other.address, 0, "0x", eta
      );
      await ethers.provider.send("evm_setNextBlockTimestamp", [eta]);
      await ethers.provider.send("evm_mine");
      await timelock.connect(admin).executeTransaction(
        other.address, 0, "0x", eta
      );
      await expect(
        timelock.connect(admin).executeTransaction(
          other.address, 0, "0x", eta
        )
      ).to.be.revertedWith("Timelock: tx not queued");
    });
  });

  // ===== Cancel Transaction =====
  describe("cancelTransaction", function () {
    it("should allow admin to cancel a queued transaction", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await timelock.connect(admin).queueTransaction(
        other.address, 0, "0x", eta
      );
      const txHash = ethers.utils.keccak256(
        ethers.utils.defaultAbiCoder.encode(
          ["address", "uint256", "bytes", "uint256"],
          [other.address, 0, "0x", eta]
        )
      );
      await timelock.connect(admin).cancelTransaction(
        other.address, 0, "0x", eta
      );
      expect(await timelock.queuedTransactions(txHash)).to.be.false;
    });

    it("should reject non-admin callers", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await timelock.connect(admin).queueTransaction(
        other.address, 0, "0x", eta
      );
      await expect(
        timelock.connect(other).cancelTransaction(
          other.address, 0, "0x", eta
        )
      ).to.be.revertedWith("Timelock: caller is not admin");
    });

    it("should reject cancelling non-existent transaction", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await expect(
        timelock.connect(admin).cancelTransaction(
          other.address, 0, "0x", eta
        )
      ).to.be.revertedWith("Timelock: tx not queued");
    });

    it("should emit CancelTransaction event", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await timelock.connect(admin).queueTransaction(
        other.address, 0, "0x", eta
      );
      const txHash = ethers.utils.keccak256(
        ethers.utils.defaultAbiCoder.encode(
          ["address", "uint256", "bytes", "uint256"],
          [other.address, 0, "0x", eta]
        )
      );
      await expect(
        timelock.connect(admin).cancelTransaction(other.address, 0, "0x", eta)
      )
        .to.emit(timelock, "CancelTransaction")
        .withArgs(txHash, other.address, 0, "0x", eta);
    });

    it("should allow cancelling expired transactions", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await timelock.connect(admin).queueTransaction(
        other.address, 0, "0x", eta
      );
      // Fast-forward past grace period
      const staleTime = eta + GRACE_PERIOD + 100;
      await ethers.provider.send("evm_setNextBlockTimestamp", [staleTime]);
      await ethers.provider.send("evm_mine");
      // Cancel should still work even though execution would be stale
      await expect(
        timelock.connect(admin).cancelTransaction(other.address, 0, "0x", eta)
      ).to.not.be.reverted;
    });
  });

  // ===== Integration: Queue → Cancel → Can't Execute =====
  describe("integration", function () {
    it("should not execute after cancel", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + MIN_DELAY;
      await timelock.connect(admin).queueTransaction(
        other.address, 0, "0x", eta
      );
      await timelock.connect(admin).cancelTransaction(
        other.address, 0, "0x", eta
      );
      await ethers.provider.send("evm_setNextBlockTimestamp", [eta]);
      await ethers.provider.send("evm_mine");
      await expect(
        timelock.connect(admin).executeTransaction(
          other.address, 0, "0x", eta
        )
      ).to.be.revertedWith("Timelock: tx not queued");
    });

    it("should handle multiple queued transactions independently", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta1 = block.timestamp + MIN_DELAY;
      const eta2 = block.timestamp + MIN_DELAY + 100;
      await timelock.connect(admin).queueTransaction(
        other.address, 0, "0x", eta1
      );
      await timelock.connect(admin).queueTransaction(
        other.address, 0, "0x", eta2
      );
      // Cancel first, execute second
      await timelock.connect(admin).cancelTransaction(
        other.address, 0, "0x", eta1
      );
      await ethers.provider.send("evm_setNextBlockTimestamp", [eta2]);
      await ethers.provider.send("evm_mine");
      await expect(
        timelock.connect(admin).executeTransaction(other.address, 0, "0x", eta2)
      ).to.not.be.reverted;
    });
  });
});
