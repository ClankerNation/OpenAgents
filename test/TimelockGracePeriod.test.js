const { expect } = require("chai");
const { ethers } = require("hardhat");

const DAY = 24 * 60 * 60;
const DELAY = 2 * DAY;
const GRACE_PERIOD = 14 * DAY;

async function deployCompat(factory, ...args) {
  const contract = await factory.deploy(...args);
  if (typeof contract.waitForDeployment === "function") {
    await contract.waitForDeployment();
  } else {
    await contract.deployed();
  }
  return contract;
}

async function getAddressCompat(contract) {
  if (typeof contract.getAddress === "function") {
    return contract.getAddress();
  }
  return contract.address;
}

async function getLatestTimestamp() {
  const block = await ethers.provider.getBlock("latest");
  return Number(block.timestamp);
}

async function setTimestamp(timestamp) {
  await ethers.provider.send("evm_setNextBlockTimestamp", [timestamp]);
  await ethers.provider.send("evm_mine", []);
}

describe("Timelock grace-period execution window", function () {
  let timelock;

  async function queueSetDelay(newDelay, eta) {
    const target = await getAddressCompat(timelock);
    const data = timelock.interface.encodeFunctionData("setDelay", [newDelay]);
    await timelock.queueTransaction(target, 0, data, eta);
    return { target, data };
  }

  beforeEach(async function () {
    const [admin] = await ethers.getSigners();
    const adminAddress = await admin.getAddress();
    const Timelock = await ethers.getContractFactory("Timelock");
    timelock = await deployCompat(Timelock, adminAddress, DELAY);
  });

  it("executes within [eta, eta + grace] window", async function () {
    const newDelay = 3 * DAY;
    const eta = (await getLatestTimestamp()) + DELAY;
    const { target, data } = await queueSetDelay(newDelay, eta);

    await setTimestamp(eta + 1);
    await timelock.executeTransaction(target, 0, data, eta);

    const updatedDelay = await timelock.delay();
    expect(updatedDelay.toString()).to.equal(newDelay.toString());
  });

  it("reverts with stale after grace period", async function () {
    const newDelay = 4 * DAY;
    const eta = (await getLatestTimestamp()) + DELAY;
    const { target, data } = await queueSetDelay(newDelay, eta);

    await setTimestamp(eta + GRACE_PERIOD + 1);

    await expect(timelock.executeTransaction(target, 0, data, eta)).to.be.revertedWith(
      "Timelock: tx stale"
    );
  });

  it("allows admin to cancel queued transaction", async function () {
    const newDelay = 5 * DAY;
    const eta = (await getLatestTimestamp()) + DELAY;
    const { target, data } = await queueSetDelay(newDelay, eta);

    await timelock.cancelTransaction(target, 0, data, eta);
    await setTimestamp(eta + 1);

    await expect(timelock.executeTransaction(target, 0, data, eta)).to.be.revertedWith(
      "Timelock: tx not queued"
    );
  });
});
