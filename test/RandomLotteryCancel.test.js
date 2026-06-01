const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("RandomLottery — refund & cancellation", function () {
  let lottery, owner, p1, p2, p3;

  beforeEach(async function () {
    [owner, p1, p2, p3] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("contracts/lottery/RandomLottery.sol:RandomLottery");
    lottery = await Factory.deploy(ethers.parseEther("0.1"));
    await lottery.waitForDeployment();
  });

  async function startAndBuy() {
    await lottery.startRound(3600, 3); // 1hr, min 3 participants
    await lottery.connect(p1).buyTicket({ value: ethers.parseEther("0.1") });
    await lottery.connect(p2).buyTicket({ value: ethers.parseEther("0.1") });
  }

  it("cancels lottery when below minimum participants after deadline", async function () {
    await startAndBuy();

    // Advance past deadline
    await ethers.provider.send("evm_increaseTime", [3601]);
    await ethers.provider.send("evm_mine");

    await lottery.cancelLottery();
    expect(await lottery.cancelled()).to.equal(true);
  });

  it("cannot cancel if minimum participants met", async function () {
    await startAndBuy();
    await lottery.connect(p3).buyTicket({ value: ethers.parseEther("0.1") });

    await ethers.provider.send("evm_increaseTime", [3601]);
    await ethers.provider.send("evm_mine");

    await expect(
      lottery.cancelLottery()
    ).to.be.revertedWith("Minimum participants met — draw instead");
  });

  it("each participant gets exact contribution back", async function () {
    await startAndBuy();

    await ethers.provider.send("evm_increaseTime", [3601]);
    await ethers.provider.send("evm_mine");

    await lottery.cancelLottery();

    const balBefore = await ethers.provider.getBalance(p1.address);
    const tx = await lottery.connect(p1).refund();
    const receipt = await tx.wait();
    const balAfter = await ethers.provider.getBalance(p1.address);
    const gasCost = receipt.gasUsed * receipt.gasPrice;

    expect(balAfter - balBefore + gasCost).to.equal(ethers.parseEther("0.1"));
  });

  it("cannot refund active lottery", async function () {
    await startAndBuy();
    await expect(lottery.connect(p1).refund()).to.be.revertedWith("Not cancelled");
  });

  it("double-refund prevented", async function () {
    await startAndBuy();

    await ethers.provider.send("evm_increaseTime", [3601]);
    await ethers.provider.send("evm_mine");

    await lottery.cancelLottery();
    await lottery.connect(p1).refund();

    await expect(lottery.connect(p1).refund()).to.be.revertedWith("No contribution");
  });
});
