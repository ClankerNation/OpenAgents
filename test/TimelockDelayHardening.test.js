const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Timelock delay hardening", function () {
  const MINIMUM_DELAY = 24 * 60 * 60;
  const MAXIMUM_DELAY = 30 * MINIMUM_DELAY;

  let admin;
  let other;
  let timelock;

  async function deployTimelock(delay = MINIMUM_DELAY) {
    [admin, other] = await ethers.getSigners();
    const Timelock = await ethers.getContractFactory("Timelock");
    timelock = await Timelock.deploy(admin.address, delay);
    await timelock.waitForDeployment();
  }

  beforeEach(async function () {
    await deployTimelock();
  });

  it("restricts delay changes to the admin", async function () {
    await expect(timelock.connect(other).setDelay(2 * MINIMUM_DELAY)).to.be.revertedWith(
      "Timelock: caller is not admin"
    );

    await expect(timelock.setDelay(2 * MINIMUM_DELAY))
      .to.emit(timelock, "NewDelay")
      .withArgs(2 * MINIMUM_DELAY);
    expect(await timelock.delay()).to.equal(2 * MINIMUM_DELAY);
  });

  it("bounds constructor and setter delays to 1-30 days", async function () {
    const Timelock = await ethers.getContractFactory("Timelock");

    await expect(Timelock.deploy(admin.address, 0)).to.be.revertedWith("Timelock: delay below min");
    await expect(Timelock.deploy(admin.address, MAXIMUM_DELAY + 1)).to.be.revertedWith(
      "Timelock: delay exceeds max"
    );

    await expect(timelock.setDelay(0)).to.be.revertedWith("Timelock: delay below min");
    await expect(timelock.setDelay(MAXIMUM_DELAY + 1)).to.be.revertedWith(
      "Timelock: delay exceeds max"
    );
  });

  it("requires queued transaction eta to respect the configured delay", async function () {
    const target = admin.address;
    const data = "0x";
    const latestBlock = await ethers.provider.getBlock("latest");

    await expect(
      timelock.queueTransaction(target, 0, data, latestBlock.timestamp + MINIMUM_DELAY - 1)
    ).to.be.revertedWith("Timelock: eta too soon");

    const afterRevertBlock = await ethers.provider.getBlock("latest");
    const eta = afterRevertBlock.timestamp + MINIMUM_DELAY + 1;
    await expect(timelock.queueTransaction(target, 0, data, eta)).to.emit(
      timelock,
      "QueueTransaction"
    );
  });
});
