const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Timelock — Issue #201: Access Control + Eta Validation", function () {
  let timelock, admin, user, target;

  beforeEach(async function () {
    [admin, user] = await ethers.getSigners();

    const Timelock = await ethers.getContractFactory("Timelock");
    timelock = await Timelock.deploy(admin.address, 86400); // 1 day delay
    await timelock.waitForDeployment();
  });

  it("execution within window (eta to eta+grace) succeeds", async function () {
    const delay = 86400; // 1 day
    const eta = (await ethers.provider.getBlock("latest")).timestamp + delay + 10;

    // Queue transaction
    await timelock.connect(admin).queueTransaction(
      admin.address, 0, "0x", eta
    );

    // Fast forward to eta
    await ethers.provider.send("evm_increaseTime", [delay + 15]);
    await ethers.provider.send("evm_mine", []);

    // Execute should succeed
    const txHash = ethers.keccak256(
      ethers.AbiCoder.defaultAbiCoder().encode(
        ["address", "uint256", "bytes", "uint256"],
        [admin.address, 0, "0x", eta]
      )
    );

    await expect(
      timelock.connect(admin).executeTransaction(admin.address, 0, "0x", eta)
    ).to.emit(timelock, "ExecuteTransaction");
  });

  it("execution after grace period reverts with 'stale'", async function () {
    const delay = 86400;
    const gracePeriod = 14 * 86400; // 14 days
    const eta = (await ethers.provider.getBlock("latest")).timestamp + delay + 10;

    await timelock.connect(admin).queueTransaction(
      admin.address, 0, "0x", eta
    );

    // Fast forward past grace period
    await ethers.provider.send("evm_increaseTime", [delay + gracePeriod + 20]);
    await ethers.provider.send("evm_mine", []);

    await expect(
      timelock.connect(admin).executeTransaction(admin.address, 0, "0x", eta)
    ).to.be.revertedWith("Timelock: tx stale");
  });

  it("non-admin cannot call setDelay", async function () {
    await expect(
      timelock.connect(user).setDelay(172800)
    ).to.be.revertedWith("Timelock: caller is not admin");
  });

  it("setDelay rejects delay below minimum", async function () {
    await expect(
      timelock.connect(admin).setDelay(0)
    ).to.be.revertedWith("Timelock: delay below minimum");
  });

  it("admin can cancel queued transactions", async function () {
    const delay = 86400;
    const eta = (await ethers.provider.getBlock("latest")).timestamp + delay + 10;

    await timelock.connect(admin).queueTransaction(
      admin.address, 0, "0x", eta
    );

    await expect(
      timelock.connect(admin).cancelTransaction(admin.address, 0, "0x", eta)
    ).to.emit(timelock, "CancelTransaction");
  });

  it("queueTransaction rejects eta too soon", async function () {
    // Eta in the past — should fail
    const pastEta = (await ethers.provider.getBlock("latest")).timestamp - 100;

    await expect(
      timelock.connect(admin).queueTransaction(admin.address, 0, "0x", pastEta)
    ).to.be.revertedWith("Timelock: eta too soon");
  });
});
