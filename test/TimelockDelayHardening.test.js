const { expect } = require("chai");
const { ethers } = require("hardhat");

const DAY = 24 * 60 * 60;

async function latestTimestamp() {
  return (await ethers.provider.getBlock("latest")).timestamp;
}

describe("Timelock delay hardening", function () {
  let owner;
  let other;
  let Timelock;

  beforeEach(async function () {
    [owner, other] = await ethers.getSigners();
    Timelock = await ethers.getContractFactory("Timelock");
  });

  async function deployWithDelay(delay = DAY) {
    const timelock = await Timelock.deploy(owner.address, delay);
    if (timelock.waitForDeployment) {
      await timelock.waitForDeployment();
    } else {
      await timelock.deployed();
    }
    return timelock;
  }

  it("enforces constructor delay bounds", async function () {
    await expect(Timelock.deploy(owner.address, DAY - 1)).to.be.revertedWith("Timelock: delay below min");
    await expect(Timelock.deploy(owner.address, 30 * DAY + 1)).to.be.revertedWith("Timelock: delay exceeds max");
  });

  it("restricts delay updates to admin and keeps them bounded", async function () {
    const timelock = await deployWithDelay();

    await expect(timelock.connect(other).setDelay(2 * DAY)).to.be.revertedWith("Timelock: caller is not admin");
    await expect(timelock.setDelay(0)).to.be.revertedWith("Timelock: delay below min");
    await expect(timelock.setDelay(31 * DAY)).to.be.revertedWith("Timelock: delay exceeds max");

    await expect(timelock.setDelay(2 * DAY)).to.emit(timelock, "NewDelay").withArgs(2 * DAY);
    expect(await timelock.delay()).to.equal(2 * DAY);
  });

  it("rejects queued transactions whose eta does not satisfy the delay", async function () {
    const timelock = await deployWithDelay();
    const eta = (await latestTimestamp()) + DAY - 1;

    await expect(timelock.queueTransaction(owner.address, 0, "0x", eta)).to.be.revertedWith(
      "Timelock: eta below delay"
    );
  });

  it("allows a valid delayed transaction to execute after eta", async function () {
    const timelock = await deployWithDelay();
    const eta = (await latestTimestamp()) + DAY + 60;

    await timelock.queueTransaction(owner.address, 0, "0x", eta);

    await ethers.provider.send("evm_setNextBlockTimestamp", [eta]);
    await ethers.provider.send("evm_mine");

    await expect(timelock.executeTransaction(owner.address, 0, "0x", eta)).to.emit(
      timelock,
      "ExecuteTransaction"
    );
  });
});
