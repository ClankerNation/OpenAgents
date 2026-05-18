const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("RandomLottery", function () {
  let lottery;
  let owner, player1, player2, player3;

  const TICKET_PRICE = ethers.utils.parseEther("0.1");
  const MIN_PARTICIPANTS = 2;
  const ROUND_DURATION = 3600; // 1 hour

  beforeEach(async function () {
    [owner, player1, player2, player3] = await ethers.getSigners();

    const RandomLottery = await ethers.getContractFactory("RandomLottery");
    lottery = await RandomLottery.deploy(TICKET_PRICE, MIN_PARTICIPANTS);
    await lottery.deployed();
  });

  describe("Deployment", function () {
    it("should set owner, ticket price, and min participants", async function () {
      expect(await lottery.owner()).to.equal(owner.address);
      expect(await lottery.ticketPrice()).to.equal(TICKET_PRICE);
      expect(await lottery.minParticipants()).to.equal(MIN_PARTICIPANTS);
    });
  });

  describe("Buy tickets", function () {
    beforeEach(async function () {
      await lottery.startRound(ROUND_DURATION);
    });

    it("should allow buying a ticket", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      const players = await lottery.getPlayers();
      expect(players).to.include(player1.address);
    });

    it("should reject wrong ticket price", async function () {
      await expect(
        lottery.connect(player1).buyTicket({ value: ethers.utils.parseEther("0.05") })
      ).to.be.revertedWith("Wrong ticket price");
    });

    it("should track contributions accurately", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      const contribution = await lottery.contributions(1, player1.address);
      expect(contribution).to.equal(TICKET_PRICE);
    });

    it("should accumulate contributions for multiple tickets", async function () {
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      const contribution = await lottery.contributions(1, player1.address);
      expect(contribution).to.equal(TICKET_PRICE.mul(2));
    });
  });

  describe("Cancel lottery", function () {
    beforeEach(async function () {
      await lottery.startRound(ROUND_DURATION);
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
    });

    it("should not allow cancellation while round active", async function () {
      await expect(lottery.cancelLottery()).to.be.revertedWith("Round still active");
    });

    it("should allow cancellation when deadline passes without enough participants", async function () {
      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();
      expect(await lottery.cancelled(1)).to.be.true;
    });

    it("should not allow cancellation if enough participants", async function () {
      await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await expect(lottery.cancelLottery()).to.be.revertedWith("Has enough participants");
    });

    it("should not allow double cancellation", async function () {
      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();
      await expect(lottery.cancelLottery()).to.be.revertedWith("Already cancelled");
    });
  });

  describe("Refund", function () {
    it("should not allow refund on active lottery", async function () {
      await lottery.startRound(ROUND_DURATION);
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await expect(lottery.connect(player1).refund()).to.be.revertedWith("Lottery not cancelled");
    });

    it("should not allow refund on completed lottery", async function () {
      await lottery.startRound(ROUND_DURATION);
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.drawWinner();
      await expect(lottery.connect(player1).refund()).to.be.revertedWith("Lottery not cancelled");
    });

    it("should refund exact contribution after cancellation", async function () {
      await lottery.startRound(ROUND_DURATION);
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      // Use high minParticipants lottery for cancellation test
      const RandomLottery = await ethers.getContractFactory("RandomLottery");
      const smallLottery = await RandomLottery.deploy(TICKET_PRICE, 5);
      await smallLottery.deployed();

      await smallLottery.startRound(ROUND_DURATION);
      await smallLottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await smallLottery.cancelLottery();

      const balanceBefore = await ethers.provider.getBalance(player1.address);
      const tx = await smallLottery.connect(player1).refund();
      const receipt = await tx.wait();
      const gasUsed = receipt.gasUsed.mul(receipt.effectiveGasPrice);

      const balanceAfter = await ethers.provider.getBalance(player1.address);
      expect(balanceAfter.sub(balanceBefore).add(gasUsed)).to.equal(TICKET_PRICE);
    });

    it("should prevent double refund", async function () {
      const RandomLottery = await ethers.getContractFactory("RandomLottery");
      const smallLottery = await RandomLottery.deploy(TICKET_PRICE, 5);
      await smallLottery.deployed();

      await smallLottery.startRound(ROUND_DURATION);
      await smallLottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await smallLottery.cancelLottery();
      await smallLottery.connect(player1).refund();

      await expect(smallLottery.connect(player1).refund()).to.be.revertedWith("Already refunded");
    });

    it("should reject refund from non-participant", async function () {
      const RandomLottery = await ethers.getContractFactory("RandomLottery");
      const smallLottery = await RandomLottery.deploy(TICKET_PRICE, 5);
      await smallLottery.deployed();

      await smallLottery.startRound(ROUND_DURATION);
      await smallLottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await smallLottery.cancelLottery();
      await expect(smallLottery.connect(player3).refund()).to.be.revertedWith("No contribution");
    });

    it("should refund all participants and leave zero balance", async function () {
      const RandomLottery = await ethers.getContractFactory("RandomLottery");
      const smallLottery = await RandomLottery.deploy(TICKET_PRICE, 5);
      await smallLottery.deployed();

      await smallLottery.startRound(ROUND_DURATION);
      await smallLottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await smallLottery.connect(player2).buyTicket({ value: TICKET_PRICE });
      await smallLottery.connect(player3).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await smallLottery.cancelLottery();

      const contractBalanceBefore = await ethers.provider.getBalance(smallLottery.address);
      expect(contractBalanceBefore).to.equal(TICKET_PRICE.mul(3));

      await smallLottery.connect(player1).refund();
      await smallLottery.connect(player2).refund();
      await smallLottery.connect(player3).refund();

      const contractBalanceAfter = await ethers.provider.getBalance(smallLottery.address);
      expect(contractBalanceAfter).to.equal(0);
    });

    it("should refund accumulated contributions for multiple tickets per player", async function () {
      const RandomLottery = await ethers.getContractFactory("RandomLottery");
      const smallLottery = await RandomLottery.deploy(TICKET_PRICE, 5);
      await smallLottery.deployed();

      await smallLottery.startRound(ROUND_DURATION);
      await smallLottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await smallLottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await smallLottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await smallLottery.cancelLottery();

      const balanceBefore = await ethers.provider.getBalance(player1.address);
      const tx = await smallLottery.connect(player1).refund();
      const receipt = await tx.wait();
      const gasUsed = receipt.gasUsed.mul(receipt.effectiveGasPrice);

      const balanceAfter = await ethers.provider.getBalance(player1.address);
      expect(balanceAfter.sub(balanceBefore).add(gasUsed)).to.equal(TICKET_PRICE.mul(3));

      expect(await ethers.provider.getBalance(smallLottery.address)).to.equal(0);
    });
  });

  describe("Draw winner", function () {
    beforeEach(async function () {
      await lottery.startRound(ROUND_DURATION);
      await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
      await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });
    });

    it("should not draw winner before round ends", async function () {
      await expect(lottery.drawWinner()).to.be.revertedWith("Round not ended");
    });

    it("should require minimum participants to draw winner", async function () {
      const RandomLottery = await ethers.getContractFactory("RandomLottery");
      const bigLottery = await RandomLottery.deploy(TICKET_PRICE, 5);
      await bigLottery.deployed();

      await bigLottery.startRound(ROUND_DURATION);
      await bigLottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await expect(bigLottery.drawWinner()).to.be.revertedWith("Not enough participants");
    });

    it("should draw a winner with enough participants", async function () {
      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await lottery.drawWinner();
      const winner = await lottery.roundWinners(1);
      expect([player1.address, player2.address]).to.include(winner);
    });

    it("should not draw winner on cancelled lottery", async function () {
      const RandomLottery = await ethers.getContractFactory("RandomLottery");
      const smallLottery = await RandomLottery.deploy(TICKET_PRICE, 5);
      await smallLottery.deployed();

      await smallLottery.startRound(ROUND_DURATION);
      await smallLottery.connect(player1).buyTicket({ value: TICKET_PRICE });

      await ethers.provider.send("evm_increaseTime", [ROUND_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await smallLottery.cancelLottery();

      // currentRound is still 1, roundEnd is 0 (reset by cancel)
      await expect(smallLottery.drawWinner()).to.be.revertedWith("Round not ended");
    });
  });
});
