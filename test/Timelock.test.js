const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Timelock", function () {
  let timelock;
  let admin, other;
  const delay = 86400; // 1 day

  beforeEach(async function () {
    [admin, other] = await ethers.getSigners();
    const Timelock = await ethers.getContractFactory("Timelock");
    timelock = await Timelock.deploy(admin.address, delay);
    await timelock.waitForDeployment();
  });

  it("rejects execution after grace period", async function () {
    const target = await timelock.getAddress();
    const value = 0;
    const data = "0x";
    const block = await ethers.provider.getBlock("latest");
    const eta = block.timestamp + delay;

    await timelock.queueTransaction(target, value, data, eta);

    // Advance time past eta + GRACE_PERIOD (14 days)
    await ethers.provider.send("evm_increaseTime", [delay + 14 * 86400 + 1]);
    await ethers.provider.send("evm_mine");

    await expect(
      timelock.executeTransaction(target, value, data, eta)
    ).to.be.revertedWith("Timelock: tx stale");
  });

  it("allows execution within window", async function () {
    const target = await timelock.getAddress();
    const value = 0;
    const data = "0x";
    const block = await ethers.provider.getBlock("latest");
    const eta = block.timestamp + delay;

    await timelock.queueTransaction(target, value, data, eta);

    // Advance time to eta
    await ethers.provider.send("evm_increaseTime", [delay + 1]);
    await ethers.provider.send("evm_mine");

    await timelock.executeTransaction(target, value, data, eta);
  });

  it("admin can cancel queued transaction", async function () {
    const target = await timelock.getAddress();
    const value = 0;
    const data = "0x";
    const block = await ethers.provider.getBlock("latest");
    const eta = block.timestamp + delay;

    await timelock.queueTransaction(target, value, data, eta);
    await timelock.cancelTransaction(target, value, data, eta);

    const txHash = ethers.keccak256(
      ethers.AbiCoder.defaultAbiCoder().encode(
        ["address", "uint256", "bytes", "uint256"],
        [target, value, data, eta]
      )
    );
    expect(await timelock.queuedTransactions(txHash)).to.equal(false);
  });

  it("reverts setDelay if not admin", async function () {
    await expect(
      timelock.connect(other).setDelay(100)
    ).to.be.revertedWith("Timelock: caller is not admin");
  });

  it("reverts setDelay if delay is 0", async function () {
    await expect(
      timelock.setDelay(0)
    ).to.be.revertedWith("Timelock: invalid delay");
  });

  it("reverts queueTransaction if eta too soon", async function () {
    const target = await timelock.getAddress();
    const block = await ethers.provider.getBlock("latest");
    const eta = block.timestamp + delay - 1; // too soon

    await expect(
      timelock.queueTransaction(target, 0, "0x", eta)
    ).to.be.revertedWith("Timelock: eta too soon");
  });
});
