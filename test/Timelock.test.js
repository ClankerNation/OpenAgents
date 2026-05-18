const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@openzeppelin/test-helpers");

describe("Timelock", function () {
  let timelock;
  let admin, user1, user2;
  const DELAY = 86400 * 2; // 2 days
  const GRACE_PERIOD = 86400 * 14; // 14 days

  beforeEach(async function () {
    [admin, user1, user2] = await ethers.getSigners();

    const Timelock = await ethers.getContractFactory("Timelock");
    timelock = await Timelock.deploy(admin.address, DELAY);
    await timelock.deployed();
  });

  describe("Deployment", function () {
    it("should set admin and delay correctly", async function () {
      expect(await timelock.admin()).to.equal(admin.address);
      expect(await timelock.delay()).to.equal(DELAY);
    });

    it("should revert if delay is below minimum", async function () {
      const Timelock = await ethers.getContractFactory("Timelock");
      await expect(Timelock.deploy(admin.address, 100)).to.be.revertedWith("Timelock: delay below min");
    });

    it("should revert if delay exceeds maximum", async function () {
      const Timelock = await ethers.getContractFactory("Timelock");
      await expect(Timelock.deploy(admin.address, 86400 * 31)).to.be.revertedWith("Timelock: delay exceeds max");
    });
  });

  describe("setDelay", function () {
    it("should allow admin to set a valid delay", async function () {
      const newDelay = 86400 * 3; // 3 days
      await expect(timelock.connect(admin).setDelay(newDelay))
        .to.emit(timelock, "NewDelay")
        .withArgs(newDelay);
      expect(await timelock.delay()).to.equal(newDelay);
    });

    it("should revert if non-admin calls setDelay", async function () {
      await expect(timelock.connect(user1).setDelay(86400 * 3)).to.be.revertedWith("Timelock: caller is not admin");
    });

    it("should revert if delay is set to 0", async function () {
      await expect(timelock.connect(admin).setDelay(0)).to.be.revertedWith("Timelock: delay below min");
    });

    it("should revert if delay is set below minimum", async function () {
      await expect(timelock.connect(admin).setDelay(86400 - 1)).to.be.revertedWith("Timelock: delay below min");
    });

    it("should revert if delay exceeds maximum", async function () {
      await expect(timelock.connect(admin).setDelay(86400 * 31)).to.be.revertedWith("Timelock: delay exceeds max");
    });
  });

  describe("queueTransaction", function () {
    it("should queue a transaction with valid eta", async function () {
      const eta = (await ethers.provider.getBlock("latest")).timestamp + DELAY;
      const txHash = await timelock.connect(admin).queueTransaction(
        user1.address, 0, "0x", eta
      );
      await expect(txHash).to.emit(timelock, "QueueTransaction");
    });

    it("should revert if eta is below block.timestamp + delay", async function () {
      const now = (await ethers.provider.getBlock("latest")).timestamp;
      const eta = now + DELAY - 1; // one second too early
      await expect(
        timelock.connect(admin).queueTransaction(user1.address, 0, "0x", eta)
      ).to.be.revertedWith("Timelock: eta below min delay");
    });

    it("should revert if non-admin queues a transaction", async function () {
      const eta = (await ethers.provider.getBlock("latest")).timestamp + DELAY;
      await expect(
        timelock.connect(user1).queueTransaction(user1.address, 0, "0x", eta)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });
  });

  describe("executeTransaction", function () {
    it("should execute within the valid window (eta <= now <= eta + GRACE_PERIOD)", async function () {
      const eta = (await ethers.provider.getBlock("latest")).timestamp + DELAY;
      await timelock.connect(admin).queueTransaction(user1.address, 0, "0x", eta);

      // Advance time past eta
      await ethers.provider.send("evm_setNextBlockTimestamp", [eta]);
      await ethers.provider.send("evm_mine");

      await expect(
        timelock.connect(admin).executeTransaction(user1.address, 0, "0x", eta)
      ).to.emit(timelock, "ExecuteTransaction");
    });

    it("should revert if executed before eta", async function () {
      const eta = (await ethers.provider.getBlock("latest")).timestamp + DELAY;
      await timelock.connect(admin).queueTransaction(user1.address, 0, "0x", eta);

      // Don't advance time — still before eta
      await expect(
        timelock.connect(admin).executeTransaction(user1.address, 0, "0x", eta)
      ).to.be.revertedWith("Timelock: eta not reached");
    });

    it("should revert after grace period (stale transaction)", async function () {
      const eta = (await ethers.provider.getBlock("latest")).timestamp + DELAY;
      await timelock.connect(admin).queueTransaction(user1.address, 0, "0x", eta);

      // Advance time past grace period
      const staleTime = eta + GRACE_PERIOD + 1;
      await ethers.provider.send("evm_setNextBlockTimestamp", [staleTime]);
      await ethers.provider.send("evm_mine");

      await expect(
        timelock.connect(admin).executeTransaction(user1.address, 0, "0x", eta)
      ).to.be.revertedWith("Timelock: tx stale");
    });

    it("should revert if transaction was not queued", async function () {
      const eta = (await ethers.provider.getBlock("latest")).timestamp + DELAY;
      await expect(
        timelock.connect(admin).executeTransaction(user1.address, 0, "0x", eta)
      ).to.be.revertedWith("Timelock: tx not queued");
    });

    it("should revert if non-admin executes a transaction", async function () {
      const eta = (await ethers.provider.getBlock("latest")).timestamp + DELAY;
      await timelock.connect(admin).queueTransaction(user1.address, 0, "0x", eta);

      await ethers.provider.send("evm_setNextBlockTimestamp", [eta]);
      await ethers.provider.send("evm_mine");

      await expect(
        timelock.connect(user1).executeTransaction(user1.address, 0, "0x", eta)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });
  });

  describe("cancelTransaction", function () {
    it("should allow admin to cancel a queued transaction", async function () {
      const eta = (await ethers.provider.getBlock("latest")).timestamp + DELAY;
      await timelock.connect(admin).queueTransaction(user1.address, 0, "0x", eta);

      await expect(
        timelock.connect(admin).cancelTransaction(user1.address, 0, "0x", eta)
      ).to.emit(timelock, "CancelTransaction");

      // Verify tx can no longer be executed after cancellation
      await ethers.provider.send("evm_setNextBlockTimestamp", [eta]);
      await ethers.provider.send("evm_mine");

      await expect(
        timelock.connect(admin).executeTransaction(user1.address, 0, "0x", eta)
      ).to.be.revertedWith("Timelock: tx not queued");
    });

    it("should revert if non-admin cancels a transaction", async function () {
      const eta = (await ethers.provider.getBlock("latest")).timestamp + DELAY;
      await timelock.connect(admin).queueTransaction(user1.address, 0, "0x", eta);

      await expect(
        timelock.connect(user1).cancelTransaction(user1.address, 0, "0x", eta)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });
  });

  describe("Admin management", function () {
    it("should allow admin to set pending admin", async function () {
      await timelock.connect(admin).setPendingAdmin(user1.address);
      expect(await timelock.pendingAdmin()).to.equal(user1.address);
    });

    it("should allow pending admin to accept admin role", async function () {
      await timelock.connect(admin).setPendingAdmin(user1.address);
      await expect(timelock.connect(user1).acceptAdmin())
        .to.emit(timelock, "NewAdmin")
        .withArgs(user1.address);
      expect(await timelock.admin()).to.equal(user1.address);
    });

    it("should revert if non-admin sets pending admin", async function () {
      await expect(
        timelock.connect(user1).setPendingAdmin(user2.address)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });

    it("should revert if non-pending admin tries to accept", async function () {
      await expect(
        timelock.connect(user1).acceptAdmin()
      ).to.be.revertedWith("Timelock: not pending admin");
    });
  });
});
