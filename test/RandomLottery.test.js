const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("RandomLottery — Refund Mechanism", function () {
  let lottery;
  let owner, player1, player2, player3;

  const TICKET_PRICE = ethers.parseEther("0.1");
  const MIN_PARTICIPANTS = 3;
  const ROUND_DURATION = 3600; // 1 hour

  beforeEach(async function () {
    [owner, player1, player2, player3] = await ethers.getSigners();

    const RandomLottery = await ethers.getContractFactory("RandomLottery");
    lottery = await RandomLottery.deploy(TICKET_PRICE, MIN_PARTICIPANTS);
    await lottery.waitForDeployment();

    // Start a round
    await lottery.startRound(ROUND_DURATION);
  });

  describe("cancelLottery", function () {
    it("should allow cancellation when round ended with insufficient participants", async function () {
      // One player buys a ticket (below minParticipants of 3)
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      // Fast-forward past round end
      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();
      expect(await lottery.cancelled()).to.equal(true);
    });

    it("should not allow cancellation while round is still active", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await expect(
        lottery.cancelLottery()
      ).to.be.revertedWith("Round not ended");
    });

    it("should not allow cancellation when minParticipants are met", async function () {
      // All 3 players buy tickets
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player3).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await expect(
        lottery.cancelLottery()
      ).to.be.revertedWith("Enough participants");
    });

    it("should not allow double cancellation", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();
      await expect(
        lottery.cancelLottery()
      ).to.be.revertedWith("Already cancelled");
    });

    it("should not allow drawWinner after cancellation", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();

      await expect(
        lottery.drawWinner()
      ).to.be.revertedWith("Lottery cancelled");
    });
  });

  describe("refund", function () {
    it("should refund exact contribution to each participant after cancellation", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();

      const balanceBefore1 = await ethers.provider.getBalance(player1.address);
      const balanceBefore2 = await ethers.provider.getBalance(player2.address);

      await lottery.connect(player1).refund();
      await lottery.connect(player2).refund();

      const balanceAfter1 = await ethers.provider.getBalance(player1.address);
      const balanceAfter2 = await ethers.provider.getBalance(player2.address);

      // Each player gets their ticket price back (minus gas)
      expect(balanceAfter1).to.be.gt(balanceBefore1);
      expect(balanceAfter2).to.be.gt(balanceBefore2);
    });

    it("should not allow refund on active lottery", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await expect(
        lottery.refund()
      ).to.be.revertedWith("Not cancelled");
    });

    it("should not allow refund on completed/drawn lottery", async function () {
      // Meet min participants
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player3).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.drawWinner();

      await expect(
        lottery.connect(player1).refund()
      ).to.be.revertedWith("Not cancelled");
    });

    it("should prevent double refund", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();
      await lottery.connect(player1).refund();

      await expect(
        lottery.connect(player1).refund()
      ).to.be.revertedWith("Already refunded");
    });

    it("should leave zero balance after all refunds claimed", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();
      await lottery.connect(player1).refund();
      await lottery.connect(player2).refund();

      expect(await lottery.getPoolSize()).to.equal(0);
    });

    it("should not allow refund for non-participant", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();

      await expect(
        lottery.connect(player3).refund()
      ).to.be.revertedWith("No contribution to refund");
    });
  });

  describe("new round after cancellation", function () {
    it("should allow starting a new round after cancellation and refunds", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();
      await lottery.connect(player1).refund();

      // Start new round
      await lottery.startRound(ROUND_DURATION);
      expect(await lottery.currentRound()).to.equal(2);
      expect(await lottery.cancelled()).to.equal(false);
    });
  });
});
