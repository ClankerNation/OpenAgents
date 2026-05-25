const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("RandomLottery refund mechanism", function () {
  let owner;
  let alice;
  let bob;
  let carol;
  let lottery;
  const ticketPrice = ethers.parseEther("1");

  beforeEach(async function () {
    [owner, alice, bob, carol] = await ethers.getSigners();
    const RandomLottery = await ethers.getContractFactory("RandomLottery");
    lottery = await RandomLottery.deploy(ticketPrice);
  });

  async function startRoundWithDeadline(offset = 100) {
    const deadline = (await time.latest()) + offset;
    await lottery.startRoundWithDeadline(deadline);
    return deadline;
  }

  it("allows public cancellation after the deadline when unique participants are below minimum", async function () {
    await lottery.setMinimumParticipants(3);
    const deadline = await startRoundWithDeadline();

    await lottery.connect(alice).buyTicket({ value: ticketPrice });
    await lottery.connect(bob).buyTicket({ value: ticketPrice });
    await lottery.connect(bob).buyTicket({ value: ticketPrice });

    expect(await lottery.roundParticipantCounts(1)).to.equal(2);
    expect(await lottery.roundBalances(1)).to.equal(ticketPrice * 3n);

    await time.increaseTo(deadline + 1);

    await expect(lottery.connect(carol).cancelLottery())
      .to.emit(lottery, "LotteryCancelled")
      .withArgs(1, 2, ticketPrice * 3n);

    expect(await lottery.roundCancelled(1)).to.equal(true);
    expect(await lottery.roundEnd()).to.equal(0);
  });

  it("refunds each participant exactly and prevents double refunds", async function () {
    await lottery.setMinimumParticipants(3);
    const deadline = await startRoundWithDeadline();

    await lottery.connect(alice).buyTicket({ value: ticketPrice });
    await lottery.connect(bob).buyTicket({ value: ticketPrice });
    await lottery.connect(bob).buyTicket({ value: ticketPrice });

    await time.increaseTo(deadline + 1);
    await lottery.cancelLottery();

    await expect(lottery.connect(alice).refund(1)).to.changeEtherBalances(
      [alice, lottery],
      [ticketPrice, -ticketPrice],
    );

    await expect(lottery.connect(bob).refund(1)).to.changeEtherBalances(
      [bob, lottery],
      [ticketPrice * 2n, -(ticketPrice * 2n)],
    );

    await expect(lottery.connect(bob).refund(1)).to.be.revertedWith("No refund");
    expect(await lottery.roundBalances(1)).to.equal(0);
    expect(await ethers.provider.getBalance(await lottery.getAddress())).to.equal(0);
  });

  it("does not refund active or completed lotteries", async function () {
    const deadline = await startRoundWithDeadline();

    await lottery.connect(alice).buyTicket({ value: ticketPrice });
    await expect(lottery.connect(alice).refund(1)).to.be.revertedWith(
      "Lottery not cancelled",
    );

    await lottery.connect(bob).buyTicket({ value: ticketPrice });
    await time.increaseTo(deadline + 1);
    await lottery.drawWinner();

    await expect(lottery.connect(alice).refund(1)).to.be.revertedWith(
      "Lottery not cancelled",
    );
    expect(await lottery.roundCompleted(1)).to.equal(true);
  });
});
