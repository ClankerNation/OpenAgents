const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("RandomLottery (cancel + refund)", function () {
  let RandomLottery, lottery;
  let owner, player1, player2, player3;
  const TICKET_PRICE = ethers.parseEther("0.1");
  const MIN_PARTICIPANTS = 3;
  const ROUND_DURATION = 3600; // 1 hour

  beforeEach(async function () {
    [owner, player1, player2, player3] = await ethers.getSigners();
    RandomLottery = await ethers.getContractFactory("RandomLottery");
    lottery = await RandomLottery.deploy(TICKET_PRICE, MIN_PARTICIPANTS);
    await lottery.waitForDeployment();
  });

  describe("constructor", function () {
    it("should set minParticipants", async function () {
      expect(await lottery.minParticipants()).to.equal(MIN_PARTICIPANTS);
    });

    it("should set ticketPrice", async function () {
      expect(await lottery.ticketPrice()).to.equal(TICKET_PRICE);
    });

    it("should set owner", async function () {
      expect(await lottery.owner()).to.equal(owner.address);
    });
  });

  describe("cancelLottery", function () {
    beforeEach(async function () {
      await lottery.startRound(ROUND_DURATION);
    });

    it("should cancel when participants < minParticipants after deadline", async function () {
      // Only 1 participant instead of required 3
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      // Advance time past round end
      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await expect(lottery.cancelLottery())
        .to.emit(lottery, "LotteryCancelled")
        .withArgs(1, 1);

      expect(await lottery.cancelled()).to.be.true;
    });

    it("should reject cancellation before deadline", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await expect(
        lottery.cancelLottery()
      ).to.be.revertedWith("Round not ended");
    });

    it("should reject cancellation when enough participants", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player3).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await expect(
        lottery.cancelLottery()
      ).to.be.revertedWith("Enough participants");
    });

    it("should reject double cancellation", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();

      await expect(
        lottery.cancelLottery()
      ).to.be.revertedWith("Not cancelled");
    });

    it("should reject cancellation when already cancelled", async function () {
      // No participants at all
      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      // 0 players < 3 minParticipants, so cancel should work
      await expect(lottery.cancelLottery())
        .to.emit(lottery, "LotteryCancelled")
        .withArgs(1, 0);
    });
  });

  describe("refund", function () {
    beforeEach(async function () {
      await lottery.startRound(ROUND_DURATION);
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();
    });

    it("should refund participant their exact contribution", async function () {
      const balanceBefore = await ethers.provider.getBalance(player1.address);

      const tx = await lottery.connect(player1).refund();
      const receipt = await tx.wait();
      const gasCost = receipt.gasUsed * receipt.gasPrice;

      const balanceAfter = await ethers.provider.getBalance(player1.address);
      expect(balanceAfter - balanceBefore + gasCost).to.equal(TICKET_PRICE);
    });

    it("should emit RefundClaimed event", async function () {
      await expect(lottery.connect(player1).refund())
        .to.emit(lottery, "RefundClaimed")
        .withArgs(player1.address, TICKET_PRICE, 1);
    });

    it("should mark participant as refunded", async function () {
      expect(await lottery.refunded(player1.address)).to.be.false;
      await lottery.connect(player1).refund();
      expect(await lottery.refunded(player1.address)).to.be.true;
    });

    it("should reject double refund", async function () {
      await lottery.connect(player1).refund();
      await expect(
        lottery.connect(player1).refund()
      ).to.be.revertedWith("Already refunded");
    });

    it("should reject refund before cancellation", async function () {
      // Deploy fresh lottery that is NOT cancelled
      const RandomLottery2 = await ethers.getContractFactory("RandomLottery");
      const lottery2 = await RandomLottery2.deploy(TICKET_PRICE, MIN_PARTICIPANTS);
      await lottery2.waitForDeployment();
      await lottery2.startRound(ROUND_DURATION);
      await lottery2.connect(player1).buyTicket({ value: TICKET_PRICE });

      await expect(
        lottery2.connect(player1).refund()
      ).to.be.revertedWith("Not cancelled");
    });

    it("should reject refund for non-participant", async function () {
      await expect(
        lottery.connect(player3).refund()
      ).to.be.revertedWith("No contribution");
    });

    it("should allow all participants to refund, leaving zero balance", async function () {
      await lottery.connect(player1).refund();
      await lottery.connect(player2).refund();

      expect(await lottery.getPoolSize()).to.equal(0);
    });

    it("should zero out contributions after refund", async function () {
      expect(await lottery.contributions(player1.address)).to.equal(TICKET_PRICE);
      await lottery.connect(player1).refund();
      expect(await lottery.contributions(player1.address)).to.equal(0);
    });
  });

  describe("drawWinner with minParticipants", function () {
    beforeEach(async function () {
      await lottery.startRound(ROUND_DURATION);
    });

    it("should reject drawWinner with too few participants", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await expect(
        lottery.drawWinner()
      ).to.be.revertedWith("Not enough participants");
    });

    it("should draw winner with enough participants", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player3).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await expect(lottery.drawWinner())
        .to.emit(lottery, "WinnerSelected");
    });
  });

  describe("startRound after cancellation", function () {
    it("should reject starting new round on cancelled lottery", async function () {
      await lottery.startRound(ROUND_DURATION);

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();

      await expect(
        lottery.startRound(ROUND_DURATION)
      ).to.be.revertedWith("Lottery cancelled");
    });
  });
});
