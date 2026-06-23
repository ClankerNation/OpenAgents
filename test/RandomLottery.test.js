const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("RandomLottery", function () {
  let lottery, owner, player1, player2, player3;

  beforeEach(async function () {
    [owner, player1, player2, player3] = await ethers.getSigners();

    const Lottery = await ethers.getContractFactory("RandomLottery");
    lottery = await Lottery.deploy(ethers.utils.parseEther("1"));
    await lottery.deployed();
  });

  describe("Basic functionality", function () {
    it("should start a round with deadline", async function () {
      await lottery.connect(owner).startRound(3600, 7200);
      expect(await lottery.currentRound()).to.equal(1);
    });

    it("should allow buying tickets", async function () {
      await lottery.connect(owner).startRound(3600, 7200);
      await lottery.connect(player1).buyTicket({ value: ethers.utils.parseEther("1") });
      expect(await lottery.roundTicketCount(1)).to.equal(1);
    });
  });

  describe("Cancel and refund", function () {
    it("should allow owner to cancel lottery after deadline with insufficient participants", async function () {
      await lottery.connect(owner).startRound(3600, 7200);
      await lottery.connect(player1).buyTicket({ value: ethers.utils.parseEther("1") });

      await ethers.provider.send("evm_setNextBlockTimestamp", [7300]);
      await ethers.provider.send("evm_mine");

      await lottery.connect(owner).cancelLottery();
    });

    it("should prevent cancel when enough participants", async function () {
      await lottery.connect(owner).startRound(3600, 7200);
      await lottery.connect(player1).buyTicket({ value: ethers.utils.parseEther("1") });
      await lottery.connect(player2).buyTicket({ value: ethers.utils.parseEther("1") });

      await ethers.provider.send("evm_setNextBlockTimestamp", [7300]);
      await ethers.provider.send("evm_mine");

      await expect(lottery.connect(owner).cancelLottery())
        .to.be.revertedWith("Enough participants — draw instead");
    });

    it("should allow participant to refund after deadline", async function () {
      const ticketPrice = ethers.utils.parseEther("1");
      await lottery.connect(owner).startRound(3600, 7200);
      await lottery.connect(player1).buyTicket({ value: ticketPrice });

      await ethers.provider.send("evm_setNextBlockTimestamp", [7300]);
      await ethers.provider.send("evm_mine");

      const balanceBefore = await ethers.provider.getBalance(player1.address);
      await lottery.connect(player1).refund();
      const balanceAfter = await ethers.provider.getBalance(player1.address);

      expect(balanceAfter).to.be.gt(balanceBefore);
    });

    it("should prevent double refund", async function () {
      const ticketPrice = ethers.utils.parseEther("1");
      await lottery.connect(owner).startRound(3600, 7200);
      await lottery.connect(player1).buyTicket({ value: ticketPrice });

      await ethers.provider.send("evm_setNextBlockTimestamp", [7300]);
      await ethers.provider.send("evm_mine");

      await lottery.connect(player1).refund();

      await expect(lottery.connect(player1).refund())
        .to.be.revertedWith("Already refunded");
    });

    it("should prevent non-participant from refunding", async function () {
      await lottery.connect(owner).startRound(3600, 7200);

      await ethers.provider.send("evm_setNextBlockTimestamp", [7300]);
      await ethers.provider.send("evm_mine");

      await expect(lottery.connect(player3).refund())
        .to.be.revertedWith("Not a participant");
    });

    it("should prevent refund before deadline", async function () {
      const ticketPrice = ethers.utils.parseEther("1");
      await lottery.connect(owner).startRound(3600, 7200);
      await lottery.connect(player1).buyTicket({ value: ticketPrice });

      await ethers.provider.send("evm_setNextBlockTimestamp", [3700]);
      await ethers.provider.send("evm_mine");

      await expect(lottery.connect(player1).refund())
        .to.be.revertedWith("Deadline not reached");
    });
  });

  describe("Winner drawing with minimum participants", function () {
    it("should require at least 2 participants to draw", async function () {
      await lottery.connect(owner).startRound(3600, 7200);
      await lottery.connect(player1).buyTicket({ value: ethers.utils.parseEther("1") });

      await ethers.provider.send("evm_setNextBlockTimestamp", [3700]);
      await ethers.provider.send("evm_mine");

      await expect(lottery.connect(owner).drawWinner())
        .to.be.revertedWith("Need at least 2 participants");
    });
  });
});
