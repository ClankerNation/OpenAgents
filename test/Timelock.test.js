const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Timelock", function () {
  let timelock;
  let admin, other;
  const DELAY = 2 * 24 * 60 * 60; // 2 days
  const GRACE_PERIOD = 14 * 24 * 60 * 60; // 14 days

  beforeEach(async function () {
    [admin, other] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("Timelock");
    timelock = await Factory.deploy(admin.address, DELAY);
    await timelock.waitForDeployment();
  });

  async function queueTx(etaOffset) {
    const block = await ethers.provider.getBlock("latest");
    const eta = block.timestamp + etaOffset + 100; // add buffer for block time
    const target = admin.address;
    const value = 0;
    const data = "0x";
    const tx = await timelock.connect(admin).queueTransaction(target, value, data, eta);
    await tx.wait();
    return { target, value, data, eta };
  }

  it("should execute within window (eta to eta + grace)", async function () {
    const params = await queueTx(DELAY);
    
    // Advance time to eta
    await ethers.provider.send("evm_setNextBlockTimestamp", [params.eta]);
    await ethers.provider.send("evm_mine");

    await expect(
      timelock.connect(admin).executeTransaction(params.target, params.value, params.data, params.eta)
    ).to.emit(timelock, "ExecuteTransaction");
  });

  it("should revert execution after grace period (stale)", async function () {
    const params = await queueTx(DELAY);
    
    // Advance time past grace period
    await ethers.provider.send("evm_setNextBlockTimestamp", [params.eta + GRACE_PERIOD + 1]);
    await ethers.provider.send("evm_mine");

    await expect(
      timelock.connect(admin).executeTransaction(params.target, params.value, params.data, params.eta)
    ).to.be.revertedWith("Timelock: tx stale");
  });

  it("should allow admin to cancel queued transaction", async function () {
    const params = await queueTx(DELAY);

    await expect(
      timelock.connect(admin).cancelTransaction(params.target, params.value, params.data, params.eta)
    ).to.emit(timelock, "CancelTransaction");

    // Verify it cannot be executed after cancellation
    await ethers.provider.send("evm_setNextBlockTimestamp", [params.eta]);
    await ethers.provider.send("evm_mine");

    await expect(
      timelock.connect(admin).executeTransaction(params.target, params.value, params.data, params.eta)
    ).to.be.revertedWith("Timelock: tx not queued");
  });

  it("should revert queue if eta is too soon", async function () {
    const block = await ethers.provider.getBlock("latest");
    const eta = block.timestamp + DELAY - 1; // Less than delay

    await expect(
      timelock.connect(admin).queueTransaction(admin.address, 0, "0x", eta)
    ).to.be.revertedWith("Timelock: eta too soon");
  });
});
