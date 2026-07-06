const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Timelock", function () {
  let timelock, target;
  let admin, other, pendingAdmin;

  const INITIAL_DELAY = 2 * 24 * 3600; // 2 days
  const GRACE_PERIOD = 14 * 24 * 3600; // 14 days

  // Helper to compute future timestamps
  async function getTimestamp() {
    const block = await ethers.provider.getBlock("latest");
    return block.timestamp;
  }

  beforeEach(async function () {
    [admin, other, pendingAdmin] = await ethers.getSigners();

    // Deploy a dummy target contract
    const MockTarget = await ethers.getContractFactory("MockTarget");
    target = await MockTarget.deploy();
    await target.waitForDeployment();

    const Timelock = await ethers.getContractFactory("Timelock");
    timelock = await Timelock.deploy(admin.address, INITIAL_DELAY);
    await timelock.waitForDeployment();
  });

  // ── constructor ──────────────────────────────────────────

  it("should deploy with correct admin and delay", async function () {
    expect(await timelock.admin()).to.equal(admin.address);
    expect(await timelock.delay()).to.equal(INITIAL_DELAY);
  });

  it("should reject delay below minimum", async function () {
    const Timelock = await ethers.getContractFactory("Timelock");
    await expect(
      Timelock.deploy(admin.address, 3600) // 1 hour < 1 day
    ).to.be.revertedWith("Timelock: delay below min");
  });

  it("should reject delay above maximum", async function () {
    const Timelock = await ethers.getContractFactory("Timelock");
    await expect(
      Timelock.deploy(admin.address, 31 * 24 * 3600) // 31 days
    ).to.be.revertedWith("Timelock: delay exceeds max");
  });

  // ── setDelay ──────────────────────────────────────────────

  it("should allow admin to set delay", async function () {
    const newDelay = 3 * 24 * 3600;
    const tx = await timelock.connect(admin).setDelay(newDelay);
    await tx.wait();
    expect(await timelock.delay()).to.equal(newDelay);
  });

  it("should emit NewDelay with old and new delay", async function () {
    const newDelay = 5 * 24 * 3600;
    await expect(timelock.connect(admin).setDelay(newDelay))
      .to.emit(timelock, "NewDelay")
      .withArgs(INITIAL_DELAY, newDelay);
  });

  it("should reject non-admin setting delay", async function () {
    await expect(
      timelock.connect(other).setDelay(3 * 24 * 3600)
    ).to.be.revertedWith("Timelock: caller is not admin");
  });

  it("should reject delay below minimum", async function () {
    await expect(
      timelock.connect(admin).setDelay(3600)
    ).to.be.revertedWith("Timelock: delay below min");
  });

  it("should reject delay above maximum", async function () {
    await expect(
      timelock.connect(admin).setDelay(31 * 24 * 3600)
    ).to.be.revertedWith("Timelock: delay exceeds max");
  });

  // ── admin transfer ────────────────────────────────────────

  it("should transfer admin via two-step process", async function () {
    await timelock.connect(admin).setPendingAdmin(pendingAdmin.address);
    await timelock.connect(pendingAdmin).acceptAdmin();
    expect(await timelock.admin()).to.equal(pendingAdmin.address);
  });

  it("should reject non-pending admin accepting", async function () {
    await timelock.connect(admin).setPendingAdmin(pendingAdmin.address);
    await expect(
      timelock.connect(other).acceptAdmin()
    ).to.be.revertedWith("Timelock: not pending admin");
  });

  it("should reject zero address as pending admin", async function () {
    await expect(
      timelock.connect(admin).setPendingAdmin(ethers.ZeroAddress)
    ).to.be.revertedWith("Timelock: zero address");
  });

  // ── queueTransaction ──────────────────────────────────────

  it("should queue a transaction with valid eta", async function () {
    const ts = await getTimestamp();
    const eta = ts + INITIAL_DELAY + 3600; // delay + 1 hour buffer

    const data = target.interface.encodeFunctionData("doSomething", [42]);
    await expect(
      timelock.connect(admin).queueTransaction(target.target, 0, data, eta)
    )
      .to.emit(timelock, "QueueTransaction");
  });

  it("should reject eta too soon (before block.timestamp + delay)", async function () {
    const ts = await getTimestamp();
    const eta = ts + 3600; // only 1 hour, but delay is 2 days

    const data = target.interface.encodeFunctionData("doSomething", [42]);
    await expect(
      timelock.connect(admin).queueTransaction(target.target, 0, data, eta)
    ).to.be.revertedWith("Timelock: eta too soon");
  });

  it("should reject duplicate transaction", async function () {
    const ts = await getTimestamp();
    const eta = ts + INITIAL_DELAY + 3600;

    const data = target.interface.encodeFunctionData("doSomething", [42]);
    await timelock.connect(admin).queueTransaction(target.target, 0, data, eta);

    await expect(
      timelock.connect(admin).queueTransaction(target.target, 0, data, eta)
    ).to.be.revertedWith("Timelock: tx already queued");
  });

  it("should reject non-admin queueing", async function () {
    const ts = await getTimestamp();
    const eta = ts + INITIAL_DELAY + 3600;

    const data = target.interface.encodeFunctionData("doSomething", [42]);
    await expect(
      timelock.connect(other).queueTransaction(target.target, 0, data, eta)
    ).to.be.revertedWith("Timelock: caller is not admin");
  });

  // ── executeTransaction ────────────────────────────────────

  it("should execute a queued transaction within window", async function () {
    const ts = await getTimestamp();
    const eta = ts + INITIAL_DELAY; // exactly at delay

    const data = target.interface.encodeFunctionData("doSomething", [42]);
    const txHash = await timelock.connect(admin).queueTransaction.staticCall(
      target.target, 0, data, eta
    );
    await timelock.connect(admin).queueTransaction(target.target, 0, data, eta);

    // Fast-forward past eta
    await ethers.provider.send("evm_setNextBlockTimestamp", [eta + 1]);
    await ethers.provider.send("evm_mine", []);

    await expect(
      timelock.connect(admin).executeTransaction(target.target, 0, data, eta)
    )
      .to.emit(timelock, "ExecuteTransaction")
      .withArgs(txHash, target.target, 0, data, eta);

    expect(await target.lastValue()).to.equal(42);
  });

  it("should revert if eta not yet reached", async function () {
    const ts = await getTimestamp();
    const eta = ts + INITIAL_DELAY + 3600;

    const data = target.interface.encodeFunctionData("doSomething", [42]);
    await timelock.connect(admin).queueTransaction(target.target, 0, data, eta);

    // Don't fast-forward — eta is still in the future
    await expect(
      timelock.connect(admin).executeTransaction(target.target, 0, data, eta)
    ).to.be.revertedWith("Timelock: eta not reached");
  });

  it("should revert if tx is stale (past grace period)", async function () {
    const ts = await getTimestamp();
    const eta = ts + INITIAL_DELAY;

    const data = target.interface.encodeFunctionData("doSomething", [42]);
    await timelock.connect(admin).queueTransaction(target.target, 0, data, eta);

    // Fast-forward past eta + GRACE_PERIOD
    await ethers.provider.send("evm_setNextBlockTimestamp", [eta + GRACE_PERIOD + 1]);
    await ethers.provider.send("evm_mine", []);

    await expect(
      timelock.connect(admin).executeTransaction(target.target, 0, data, eta)
    ).to.be.revertedWith("Timelock: tx stale");
  });

  it("should revert if tx not queued", async function () {
    const ts = await getTimestamp();
    const eta = ts + INITIAL_DELAY;

    const data = target.interface.encodeFunctionData("doSomething", [42]);
    await expect(
      timelock.connect(admin).executeTransaction(target.target, 0, data, eta)
    ).to.be.revertedWith("Timelock: tx not queued");
  });

  it("should prevent double execution", async function () {
    const ts = await getTimestamp();
    const eta = ts + INITIAL_DELAY;

    const data = target.interface.encodeFunctionData("doSomething", [42]);
    await timelock.connect(admin).queueTransaction(target.target, 0, data, eta);

    // Fast-forward past eta
    await ethers.provider.send("evm_setNextBlockTimestamp", [eta + 1]);
    await ethers.provider.send("evm_mine", []);

    await timelock.connect(admin).executeTransaction(target.target, 0, data, eta);

    // Second execution should fail
    await expect(
      timelock.connect(admin).executeTransaction(target.target, 0, data, eta)
    ).to.be.revertedWith("Timelock: tx not queued");
  });

  // ── cancelTransaction ─────────────────────────────────────

  it("should cancel a queued transaction", async function () {
    const ts = await getTimestamp();
    const eta = ts + INITIAL_DELAY + 3600;

    const data = target.interface.encodeFunctionData("doSomething", [42]);
    const txHash = await timelock.connect(admin).queueTransaction.staticCall(
      target.target, 0, data, eta
    );
    await timelock.connect(admin).queueTransaction(target.target, 0, data, eta);

    await expect(
      timelock.connect(admin).cancelTransaction(target.target, 0, data, eta)
    )
      .to.emit(timelock, "CancelTransaction")
      .withArgs(txHash, target.target, 0, data, eta);

    // Verify cannot execute after cancel
    await ethers.provider.send("evm_setNextBlockTimestamp", [eta + 1]);
    await ethers.provider.send("evm_mine", []);

    await expect(
      timelock.connect(admin).executeTransaction(target.target, 0, data, eta)
    ).to.be.revertedWith("Timelock: tx not queued");
  });

  it("should revert cancel of non-queued tx", async function () {
    const ts = await getTimestamp();
    const eta = ts + INITIAL_DELAY;

    const data = target.interface.encodeFunctionData("doSomething", [42]);
    await expect(
      timelock.connect(admin).cancelTransaction(target.target, 0, data, eta)
    ).to.be.revertedWith("Timelock: tx not queued");
  });

  it("should reject non-admin cancel", async function () {
    const ts = await getTimestamp();
    const eta = ts + INITIAL_DELAY + 3600;

    const data = target.interface.encodeFunctionData("doSomething", [42]);
    await timelock.connect(admin).queueTransaction(target.target, 0, data, eta);

    await expect(
      timelock.connect(other).cancelTransaction(target.target, 0, data, eta)
    ).to.be.revertedWith("Timelock: caller is not admin");
  });

  // ── GRACE_PERIOD boundary ─────────────────────────────────

  it("should execute at exact grace period boundary (eta + GRACE_PERIOD)", async function () {
    const ts = await getTimestamp();
    const eta = ts + INITIAL_DELAY;

    const data = target.interface.encodeFunctionData("doSomething", [99]);
    await timelock.connect(admin).queueTransaction(target.target, 0, data, eta);

    // Fast-forward to exact eta + GRACE_PERIOD (inclusive)
    await ethers.provider.send("evm_setNextBlockTimestamp", [eta + GRACE_PERIOD]);
    await ethers.provider.send("evm_mine", []);

    await expect(
      timelock.connect(admin).executeTransaction(target.target, 0, data, eta)
    ).to.not.be.reverted;
  });

  it("should revert at exact grace period + 1 second", async function () {
    const ts = await getTimestamp();
    const eta = ts + INITIAL_DELAY;

    const data = target.interface.encodeFunctionData("doSomething", [99]);
    await timelock.connect(admin).queueTransaction(target.target, 0, data, eta);

    // Fast-forward to eta + GRACE_PERIOD + 1 (exclusive)
    await ethers.provider.send("evm_setNextBlockTimestamp", [eta + GRACE_PERIOD + 1]);
    await ethers.provider.send("evm_mine", []);

    await expect(
      timelock.connect(admin).executeTransaction(target.target, 0, data, eta)
    ).to.be.revertedWith("Timelock: tx stale");
  });
});
