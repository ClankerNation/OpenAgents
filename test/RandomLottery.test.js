const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("RandomLottery (issue #167 — refund mechanism)", function () {
  let lottery;
  let owner, player1, player2, player3;
  const TICKET_PRICE = ethers.parseEther("0.1");
  const MIN_PARTICIPANTS = 2;
  const ROUND_DURATION = 3600; // 1 hour

  beforeEach(async function () {
    [owner, player1, player2, player3] = await ethers.getSigners();
    const Lottery = await ethers.getContractFactory("RandomLottery");
    lottery = await Lottery.deploy(TICKET_PRICE, MIN_PARTICIPANTS);
    await lottery.waitForDeployment();
  });

  describe("lifecycle", function () {
    it("starts a round with deadline = end time", async function () {
      await lottery.connect(owner).startRound(ROUND_DURATION, 0);
      const info = await lottery.getRoundInfo(1);
      expect(info.deadline).to.be.gt(0);
      expect(info.cancelled).to.be.false;
      expect(info.completed).to.be.false;
    });
  });

  describe("cancelLottery", function () {
    it("reverts if called before deadline", async function () {
      await lottery.connect(owner).startRound(ROUND_DURATION, 5);
      await player1.sendTransaction({ to: await lottery.getAddress(), value: TICKET_PRICE });
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await expect(lottery.connect(owner).cancelLottery(1)).to.be.revertedWith("Round not ended yet");
    });

    it("cancels after deadline if below min participants", async function () {
      await lottery.connect(owner).startRound(ROUND_DURATION, 5);
      // Only 1 player (< minParticipants=5)
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      // Advance past deadline
      await time.increase(ROUND_DURATION + 1);
      await expect(lottery.connect(owner).cancelLottery(1)).to.not.be.reverted;
      const info = await lottery.getRoundInfo(1);
      expect(info.cancelled).to.be.true;
    });

    it("reverts if min participants was reached", async function () {
      await lottery.connect(owner).startRound(ROUND_DURATION, 2);
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });
      await time.increase(ROUND_DURATION + 1);
      await expect(lottery.connect(owner).cancelLottery(1)).to.be.revertedWith(
        "Round reached min participants; cannot cancel"
      );
    });

    it("reverts if already cancelled", async function () {
      await lottery.connect(owner).startRound(ROUND_DURATION, 5);
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await time.increase(ROUND_DURATION + 1);
      await lottery.connect(owner).cancelLottery(1);
      await expect(lottery.connect(owner).cancelLottery(1)).to.be.revertedWith("Already cancelled");
    });

    it("reverts if non-owner tries to cancel", async function () {
      await lottery.connect(owner).startRound(ROUND_DURATION, 5);
      await time.increase(ROUND_DURATION + 1);
      await expect(lottery.connect(player1).cancelLottery(1)).to.be.revertedWith("Not owner");
    });
  });

  describe("refund", function () {
    beforeEach(async function () {
      // Round 1: 3 players enter, set min to 5 so it gets cancelled
      await lottery.connect(owner).startRound(ROUND_DURATION, 5);
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player3).buyTicket({ value: TICKET_PRICE });
      await time.increase(ROUND_DURATION + 1);
      await lottery.connect(owner).cancelLottery(1);
    });

    it("reverts if round not cancelled", async function () {
      // Set up a new active round
      await lottery.connect(owner).startRound(ROUND_DURATION, 0);
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await expect(lottery.connect(player1).refund(2)).to.be.revertedWith("Round not cancelled");
    });

    it("refunds a participant their exact contribution", async function () {
      const before = await ethers.provider.getBalance(player1.address);
      const tx = await lottery.connect(player1).refund(1);
      const receipt = await tx.wait();
      const gasUsed = receipt.gasUsed * receipt.gasPrice;
      const after = await ethers.provider.getBalance(player1.address);
      // Player1 paid TICKET_PRICE; refund should give them TICKET_PRICE back (minus gas)
      expect(after - before + gasUsed).to.equal(TICKET_PRICE);
    });

    it("prevents double refund", async function () {
      await lottery.connect(player1).refund(1);
      await expect(lottery.connect(player1).refund(1)).to.be.revertedWith("Already refunded");
    });

    it("reverts for non-participant", async function () {
      // owner never bought a ticket
      await expect(lottery.connect(owner).refund(1)).to.be.revertedWith("No contribution");
    });

    it("remaining balance is zero after all refunds", async function () {
      await lottery.connect(player1).refund(1);
      await lottery.connect(player2).refund(1);
      await lottery.connect(player3).refund(1);
      const remaining = await lottery.getPoolSize();
      expect(remaining).to.equal(0);
    });
  });
});
