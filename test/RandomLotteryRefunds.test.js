const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("RandomLottery refunds", function () {
  const ticketPrice = ethers.parseEther("1");

  async function deployLottery() {
    const Lottery = await ethers.getContractFactory("RandomLottery");
    const lottery = await Lottery.deploy(ticketPrice);
    await lottery.waitForDeployment();
    return lottery;
  }

  it("allows anyone to cancel after the deadline when minimum participation is not met", async function () {
    const [, alice, bob] = await ethers.getSigners();
    const lottery = await deployLottery();

    await lottery["startRound(uint256,uint256)"](60, 3);
    await lottery.connect(alice).buyTicket({ value: ticketPrice });
    await lottery.connect(bob).buyTicket({ value: ticketPrice });
    await time.increase(61);

    await expect(lottery.connect(alice).cancelLottery())
      .to.emit(lottery, "LotteryCancelled")
      .withArgs(1);

    expect(await lottery.roundCancelled(1)).to.equal(true);
    expect(await lottery.getRoundPoolSize(1)).to.equal(ticketPrice * 2n);
  });

  it("refunds each participant exactly and empties the cancelled round balance", async function () {
    const [, alice, bob] = await ethers.getSigners();
    const lottery = await deployLottery();

    await lottery["startRound(uint256,uint256)"](60, 3);
    await lottery.connect(alice).buyTicket({ value: ticketPrice });
    await lottery.connect(bob).buyTicket({ value: ticketPrice });
    await time.increase(61);
    await lottery.cancelLottery();

    await expect(lottery.connect(alice).refund(1))
      .to.changeEtherBalances([lottery, alice], [-ticketPrice, ticketPrice]);
    await expect(lottery.connect(bob).refund(1))
      .to.changeEtherBalances([lottery, bob], [-ticketPrice, ticketPrice]);

    expect(await lottery.contributions(1, alice.address)).to.equal(0);
    expect(await lottery.contributions(1, bob.address)).to.equal(0);
    expect(await lottery.getRoundPoolSize(1)).to.equal(0);
    expect(await ethers.provider.getBalance(await lottery.getAddress())).to.equal(0);
  });

  it("prevents double refunds", async function () {
    const [, alice] = await ethers.getSigners();
    const lottery = await deployLottery();

    await lottery["startRound(uint256,uint256)"](60, 2);
    await lottery.connect(alice).buyTicket({ value: ticketPrice });
    await time.increase(61);
    await lottery.cancelLottery();

    await lottery.connect(alice).refund(1);
    await expect(lottery.connect(alice).refund(1)).to.be.revertedWith("Nothing to refund");
  });

  it("does not allow refunds for active or completed lotteries", async function () {
    const [, alice, bob] = await ethers.getSigners();
    const lottery = await deployLottery();

    await lottery["startRound(uint256,uint256)"](60, 2);
    await lottery.connect(alice).buyTicket({ value: ticketPrice });
    await expect(lottery.connect(alice).refund(1)).to.be.revertedWith("Lottery not cancelled");

    await lottery.connect(bob).buyTicket({ value: ticketPrice });
    await time.increase(61);
    await lottery.drawWinner();

    await expect(lottery.connect(alice).refund(1)).to.be.revertedWith("Lottery not cancelled");
  });
});
