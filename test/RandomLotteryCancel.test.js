const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("RandomLottery — cancellation & refund", function () {
  let lottery, owner, p1, p2, p3;

  const TICKET_PRICE = ethers.parseEther("0.1");
  const ROUND_DURATION = 3600; // 1 hour
  const MIN_PARTICIPANTS = 3;

  beforeEach(async function () {
    [owner, p1, p2, p3] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("RandomLottery");
    lottery = await Factory.deploy(TICKET_PRICE);
    await lottery.waitForDeployment();
  });

  async function startAndBuyTwo() {
    const tx = await lottery.startRound(ROUND_DURATION, MIN_PARTICIPANTS);
    await tx.wait();
    await lottery.connect(p1).buyTicket({ value: TICKET_PRICE });
    await lottery.connect(p2).buyTicket({ value: TICKET_PRICE });
  }

  async function startAndBuyThree() {
    const tx = await lottery.startRound(ROUND_DURATION, MIN_PARTICIPANTS);
    await tx.wait();
    await lottery.connect(p1).buyTicket({ value: TICKET_PRICE });
    await lottery.connect(p2).buyTicket({ value: TICKET_PRICE });
    await lottery.connect(p3).buyTicket({ value: TICKET_PRICE });
  }

  async function advancePastDeadline() {
    await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
    await ethers.provider.send("evm_mine");
  }

  describe("Cancellation", function () {
    it("should cancel when below minimum participants after deadline", async function () {
      await startAndBuyTwo();
      await advancePastDeadline();

      const tx = await lottery.cancelLottery();
      await tx.wait();

      expect(await lottery.cancelled(1)).to.equal(true);
    });

    it("should emit LotteryCancelled event on cancellation", async function () {
      await startAndBuyTwo();
      await advancePastDeadline();

      await expect(lottery.cancelLottery())
        .to.emit(lottery, "LotteryCancelled")
        .withArgs(1);
    });

    it("should not cancel if minimum participants met", async function () {
      await startAndBuyThree();
      await advancePastDeadline();

      await expect(
        lottery.cancelLottery()
      ).to.be.revertedWith("Minimum participants met - draw instead");
    });

    it("should not cancel while round is still active", async function () {
      await startAndBuyTwo();
      // Don't advance time — round still active

      await expect(
        lottery.cancelLottery()
      ).to.be.revertedWith("Round still active");
    });

    it("should not cancel twice", async function () {
      await startAndBuyTwo();
      await advancePastDeadline();

      await lottery.cancelLottery();
      await expect(
        lottery.cancelLottery()
      ).to.be.revertedWith("Already cancelled");
    });

    it("should block buyTicket after cancellation", async function () {
      await startAndBuyTwo();
      await advancePastDeadline();
      await lottery.cancelLottery();

      await expect(
        lottery.connect(p3).buyTicket({ value: TICKET_PRICE })
      ).to.be.revertedWith("Round cancelled");
    });

    it("should block drawWinner after cancellation", async function () {
      await startAndBuyTwo();
      await advancePastDeadline();
      await lottery.cancelLottery();

      await expect(
        lottery.drawWinner()
      ).to.be.revertedWith("Round cancelled");
    });
  });

  describe("Refund", function () {
    it("should refund exact contribution to each participant", async function () {
      await startAndBuyTwo();
      await advancePastDeadline();
      await lottery.cancelLottery();

      const balBefore1 = await ethers.provider.getBalance(p1.address);
      const tx1 = await lottery.connect(p1).refund();
      const receipt1 = await tx1.wait();
      const balAfter1 = await ethers.provider.getBalance(p1.address);
      const gasCost1 = receipt1.gasUsed * receipt1.gasPrice;
      expect(balAfter1 - balBefore1 + gasCost1).to.equal(TICKET_PRICE);

      const balBefore2 = await ethers.provider.getBalance(p2.address);
      const tx2 = await lottery.connect(p2).refund();
      const receipt2 = await tx2.wait();
      const balAfter2 = await ethers.provider.getBalance(p2.address);
      const gasCost2 = receipt2.gasUsed * receipt2.gasPrice;
      expect(balAfter2 - balBefore2 + gasCost2).to.equal(TICKET_PRICE);
    });

    it("should emit RefundClaimed event", async function () {
      await startAndBuyTwo();
      await advancePastDeadline();
      await lottery.cancelLottery();

      await expect(lottery.connect(p1).refund())
        .to.emit(lottery, "RefundClaimed")
        .withArgs(p1.address, TICKET_PRICE, 1);
    });

    it("should not refund active (non-cancelled) lottery", async function () {
      await startAndBuyTwo();
      await advancePastDeadline();
      // Don't cancel — round just ended

      await expect(
        lottery.connect(p1).refund()
      ).to.be.revertedWith("Not cancelled");
    });

    it("should not allow double refund", async function () {
      await startAndBuyTwo();
      await advancePastDeadline();
      await lottery.cancelLottery();

      await lottery.connect(p1).refund();
      await expect(
        lottery.connect(p1).refund()
      ).to.be.revertedWith("Already refunded");
    });

    it("should not allow refund from non-participant", async function () {
      await startAndBuyTwo();
      await advancePastDeadline();
      await lottery.cancelLottery();

      await expect(
        lottery.connect(p3).refund()
      ).to.be.revertedWith("No contribution");
    });

    it("should leave zero balance after all refunds", async function () {
      await startAndBuyTwo();
      await advancePastDeadline();
      await lottery.cancelLottery();

      await lottery.connect(p1).refund();
      await lottery.connect(p2).refund();

      const balance = await ethers.provider.getBalance(lottery.target);
      expect(balance).to.equal(0);
    });
  });
});
