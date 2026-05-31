const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Timelock", function () {
  const DELAY = 2 * 24 * 60 * 60;
  const GRACE_PERIOD = 14 * 24 * 60 * 60;

  let timelock;
  let admin;
  let target;

  async function mineAt(timestamp) {
    await ethers.provider.send("evm_setNextBlockTimestamp", [timestamp]);
    await ethers.provider.send("evm_mine");
  }

  async function queueSimpleTransaction() {
    const latest = await ethers.provider.getBlock("latest");
    const eta = latest.timestamp + DELAY + 10;
    const value = 0;
    const data = "0x";

    await timelock.queueTransaction(target.address, value, data, eta);
    return { eta, value, data };
  }

  beforeEach(async function () {
    [admin, target] = await ethers.getSigners();

    const Timelock = await ethers.getContractFactory("Timelock");
    timelock = await Timelock.deploy(admin.address, DELAY);
    await timelock.waitForDeployment();
  });

  it("executes queued transactions within [eta, eta + grace]", async function () {
    const { eta, value, data } = await queueSimpleTransaction();

    await mineAt(eta + 1);

    await expect(timelock.executeTransaction(target.address, value, data, eta))
      .to.emit(timelock, "ExecuteTransaction");
  });

  it("reverts execution after grace period with stale", async function () {
    const { eta, value, data } = await queueSimpleTransaction();

    await mineAt(eta + GRACE_PERIOD + 1);

    await expect(
      timelock.executeTransaction(target.address, value, data, eta)
    ).to.be.revertedWith("Timelock: tx stale");
  });

  it("allows admin to cancel queued transactions", async function () {
    const { eta, value, data } = await queueSimpleTransaction();

    await expect(timelock.cancelTransaction(target.address, value, data, eta))
      .to.emit(timelock, "CancelTransaction");

    await mineAt(eta + 1);

    await expect(
      timelock.executeTransaction(target.address, value, data, eta)
    ).to.be.revertedWith("Timelock: tx not queued");
  });
});
