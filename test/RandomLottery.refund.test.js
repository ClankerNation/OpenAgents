const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("RandomLottery refund flow", function () {
  let lottery;
  let owner, alice, bob;
  const ticketPrice = ethers.parseEther("1");

  async function endRound(seconds = 3601) {
    await ethers.provider.send("evm_increaseTime", [seconds]);
    await ethers.provider.send("evm_mine");
  }

  beforeEach(async function () {
    [owner, alice, bob] = await ethers.getSigners();
    const RandomLottery = await ethers.getContractFactory("RandomLottery");
    lottery = await RandomLottery.deploy(ticketPrice);
    await lottery.waitForDeployment();
  });

  it("cancels after deadline when minimum participants are not reached", async function () {
    await lottery.startRound(3600);
    await lottery.connect(alice).buyTicket({ value: ticketPrice });

    await endRound();

    await expect(lottery.cancelLottery())
      .to.emit(lottery, "LotteryCancelled")
      .withArgs(1n, ticketPrice);

    expect(await lottery.roundCancelled()).to.equal(true);
    expect(await lottery.roundEnd()).to.equal(0n);
  });

  it("refunds exact contribution after cancellation and prevents double refund", async function () {
    await lottery.startRound(3600);
    await lottery.connect(alice).buyTicket({ value: ticketPrice });

    await endRound();
    await lottery.cancelLottery();

    const round = await lottery.currentRound();
    const contributed = await lottery.contributions(round, alice.address);
    expect(contributed).to.equal(ticketPrice);

    await expect(lottery.connect(alice).refund())
      .to.emit(lottery, "Refunded")
      .withArgs(alice.address, ticketPrice, round);

    expect(await lottery.contributions(round, alice.address)).to.equal(0n);
    expect(await lottery.pendingRefundPool()).to.equal(0n);
    expect(await lottery.getPoolSize()).to.equal(0n);

    await expect(lottery.connect(alice).refund()).to.be.revertedWith("Nothing to refund");
  });

  it("does not allow refunds when lottery is active or completed", async function () {
    await lottery.startRound(3600);
    await lottery.connect(alice).buyTicket({ value: ticketPrice });

    await expect(lottery.connect(alice).refund()).to.be.revertedWith("Round not cancelled");

    await lottery.connect(bob).buyTicket({ value: ticketPrice });
    await endRound();
    await lottery.drawWinner();

    await expect(lottery.connect(alice).refund()).to.be.revertedWith("Round not cancelled");
  });
});
