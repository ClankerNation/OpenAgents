const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PrizeSplit security hardening", function () {
  async function deploy() {
    const [admin, winner1, winner2, winner3] = await ethers.getSigners();
    const PrizeSplit = await ethers.getContractFactory("PrizeSplit");
    const prizeSplit = await PrizeSplit.deploy();
    await prizeSplit.waitForDeployment();
    return { prizeSplit, admin, winner1, winner2, winner3 };
  }

  it("rejects empty, zero-address, and duplicate winner lists", async function () {
    const { prizeSplit, admin, winner1 } = await deploy();
    await prizeSplit.connect(admin).fundRound({ value: 10n });

    await expect(prizeSplit.finalizeRound(1n, [])).to.be.revertedWith("No winners");
    await expect(prizeSplit.finalizeRound(1n, [ethers.ZeroAddress])).to.be.revertedWith("Zero winner");
    await expect(prizeSplit.finalizeRound(1n, [winner1.address, winner1.address])).to.be.revertedWith(
      "Duplicate winner"
    );
  });

  it("assigns all rounding dust to the final winner", async function () {
    const { prizeSplit, admin, winner1, winner2, winner3 } = await deploy();
    await prizeSplit.connect(admin).fundRound({ value: 100n });
    await prizeSplit.finalizeRound(1n, [winner1.address, winner2.address, winner3.address]);

    expect(await prizeSplit.getShare(1n, winner1.address)).to.equal(33n);
    expect(await prizeSplit.getShare(1n, winner2.address)).to.equal(33n);
    expect(await prizeSplit.getShare(1n, winner3.address)).to.equal(34n);

    await prizeSplit.connect(winner1).claimPrize(1n);
    await prizeSplit.connect(winner2).claimPrize(1n);
    await prizeSplit.connect(winner3).claimPrize(1n);
    expect(await ethers.provider.getBalance(await prizeSplit.getAddress())).to.equal(0n);
  });

  it("blocks reentrant claims while preserving the winner's claim state", async function () {
    const { prizeSplit, admin } = await deploy();
    const ReentrantWinner = await ethers.getContractFactory("ReentrantWinner");
    const attacker = await ReentrantWinner.deploy();
    await attacker.waitForDeployment();
    await prizeSplit.connect(admin).fundRound({ value: 100n });
    await prizeSplit.finalizeRound(1n, [await attacker.getAddress()]);

    await attacker.attack(await prizeSplit.getAddress(), 1n);

    expect(await attacker.reentrySucceeded()).to.equal(false);
    expect(await prizeSplit.isClaimed(1n, await attacker.getAddress())).to.equal(true);
    expect(await ethers.provider.getBalance(await prizeSplit.getAddress())).to.equal(0n);
  });
});
