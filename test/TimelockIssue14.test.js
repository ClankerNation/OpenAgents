const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Timelock delay hardening", function () {
  const MINIMUM_DELAY = 24n * 60n * 60n;
  const MAXIMUM_DELAY = 30n * 24n * 60n * 60n;

  async function deployFixture(delay = MINIMUM_DELAY) {
    const [admin, other] = await ethers.getSigners();
    const Timelock = await ethers.getContractFactory("Timelock");
    const timelock = await Timelock.deploy(admin.address, delay);
    await timelock.waitForDeployment();
    const Target = await ethers.getContractFactory("TimelockTestTarget");
    const target = await Target.deploy();
    await target.waitForDeployment();
    return { admin, other, timelock, target };
  }

  it("enforces the one-to-thirty-day constructor bounds", async function () {
    const Timelock = await ethers.getContractFactory("Timelock");

    await expect(Timelock.deploy(ethers.Wallet.createRandom().address, MINIMUM_DELAY - 1n))
      .to.be.revertedWith("Timelock: delay below min");
    await expect(Timelock.deploy(ethers.Wallet.createRandom().address, MAXIMUM_DELAY + 1n))
      .to.be.revertedWith("Timelock: delay exceeds max");

    const timelock = await Timelock.deploy(ethers.Wallet.createRandom().address, MINIMUM_DELAY);
    expect(await timelock.delay()).to.equal(MINIMUM_DELAY);
  });

  it("allows only the admin to set a bounded delay", async function () {
    const { admin, other, timelock } = await deployFixture();

    await expect(timelock.connect(other).setDelay(MINIMUM_DELAY + 1n)).to.be.revertedWith(
      "Timelock: caller is not admin"
    );
    await expect(timelock.connect(admin).setDelay(MINIMUM_DELAY - 1n)).to.be.revertedWith(
      "Timelock: delay below min"
    );
    await expect(timelock.connect(admin).setDelay(MAXIMUM_DELAY + 1n)).to.be.revertedWith(
      "Timelock: delay exceeds max"
    );

    await timelock.connect(admin).setDelay(MINIMUM_DELAY + 1n);
    expect(await timelock.delay()).to.equal(MINIMUM_DELAY + 1n);
  });

  it("rejects queue eta values that do not include the configured delay", async function () {
    const { admin, timelock, target } = await deployFixture();
    const data = target.interface.encodeFunctionData("setValue", [42n]);
    const latest = await ethers.provider.getBlock("latest");
    const tooSoon = BigInt(latest.timestamp) + MINIMUM_DELAY - 1n;

    await expect(timelock.connect(admin).queueTransaction(await target.getAddress(), 0, data, tooSoon))
      .to.be.revertedWith("Timelock: eta too soon");
  });

  it("enforces the delay before a queued call can execute", async function () {
    const { admin, timelock, target } = await deployFixture();
    const data = target.interface.encodeFunctionData("setValue", [42n]);
    const latest = await ethers.provider.getBlock("latest");
    const eta = BigInt(latest.timestamp) + MINIMUM_DELAY + 2n;

    await timelock.connect(admin).queueTransaction(await target.getAddress(), 0, data, eta);
    await expect(
      timelock.connect(admin).executeTransaction(await target.getAddress(), 0, data, eta)
    ).to.be.revertedWith("Timelock: eta not reached");

    await ethers.provider.send("evm_setNextBlockTimestamp", [Number(eta)]);
    await ethers.provider.send("evm_mine");
    await timelock.connect(admin).executeTransaction(await target.getAddress(), 0, data, eta);
    expect(await target.value()).to.equal(42n);
  });
});
