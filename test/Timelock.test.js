const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Timelock - Issue #201", function () {
  let timelock;
  let admin, nonAdmin, target;
  const ONE_DAY = 86400;
  const DELAY = ONE_DAY * 2;

  beforeEach(async function () {
    [admin, nonAdmin, target] = await ethers.getSigners();
    const Timelock = await ethers.getContractFactory("Timelock");
    timelock = await Timelock.deploy(admin.address, DELAY);
    await timelock.waitForDeployment();
  });

  describe("MINIMUM_DELAY constant", function () {
    it("should have MINIMUM_DELAY of 1 day", async function () {
      expect(await timelock.MINIMUM_DELAY()).to.equal(ONE_DAY);
    });
  });

  describe("setDelay access control", function () {
    it("should allow admin to set delay", async function () {
      const newDelay = ONE_DAY * 5;
      await expect(timelock.connect(admin).setDelay(newDelay))
        .to.emit(timelock, "NewDelay")
        .withArgs(newDelay);
      expect(await timelock.delay()).to.equal(newDelay);
    });

    it("should revert when non-admin calls setDelay", async function () {
      await expect(
        timelock.connect(nonAdmin).setDelay(ONE_DAY * 5)
      ).to.be.revertedWith("Timelock: caller is not admin");
    });

    it("should revert when delay is below MINIMUM_DELAY", async function () {
      await expect(
        timelock.connect(admin).setDelay(ONE_DAY - 1)
      ).to.be.revertedWith("Timelock: delay below minimum");
    });

    it("should revert when delay exceeds MAXIMUM_DELAY", async function () {
      await expect(
        timelock.connect(admin).setDelay(30 * ONE_DAY + 1)
      ).to.be.revertedWith("Timelock: delay exceeds max");
    });
  });

  describe("constructor validation", function () {
    it("should revert if initial delay is below MINIMUM_DELAY", async function () {
      const Timelock = await ethers.getContractFactory("Timelock");
      await expect(
        Timelock.deploy(admin.address, ONE_DAY - 1)
      ).to.be.revertedWith("Timelock: delay below minimum");
    });
  });

  describe("queueTransaction eta validation", function () {
    it("should revert if eta is too soon (before block.timestamp + delay)", async function () {
      const eta = (await ethers.provider.getBlock("latest")).timestamp + DELAY - 10;
      await expect(
        timelock.connect(admin).queueTransaction(target.address, 0, "0x", eta)
      ).to.be.revertedWith("Timelock: eta too soon");
    });

    it("should succeed if eta >= block.timestamp + delay", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + DELAY + 10;
      await expect(
        timelock.connect(admin).queueTransaction(target.address, 0, "0x", eta)
      ).to.not.be.reverted;
    });
  });

  describe("cancelTransaction", function () {
    it("should allow admin to cancel a queued transaction", async function () {
      const block = await ethers.provider.getBlock("latest");
      const eta = block.timestamp + DELAY + 10;
      const txHash = ethers.keccak256(
        ethers.AbiCoder.defaultAbiCoder().encode(
          ["address", "uint256", "bytes", "uint256"],
          [target.address, 0, "0x", eta]
        )
      );
      await timelock.connect(admin).queueTransaction(target.address, 0, "0x", eta);
      await timelock.connect(admin).cancelTransaction(target.address, 0, "0x", eta);
      expect(await timelock.queuedTransactions(txHash)).to.equal(false);
    });
  });
});
