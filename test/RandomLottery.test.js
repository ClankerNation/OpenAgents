const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("RandomLottery", function () {
  let Lottery, lottery, owner, addr1, addr2, addr3;
  let ticketPrice;
  let minParticipants = 4;

  beforeEach(async function () {
    [owner, addr1, addr2, addr3] = await ethers.getSigners();
    Lottery = await ethers.getContractFactory("RandomLottery");
    ticketPrice = ethers.parseEther("0.1");

    // set deadline to 1 day in the future
    const latestBlock = await ethers.provider.getBlock("latest");
    const deadline = latestBlock.timestamp + 86400;

    lottery = await Lottery.deploy(ticketPrice, deadline, minParticipants);
  });

  describe("Cancellation & Refunds", function () {
    it("should allow owner to cancel if deadline passed and min participants not met", async function () {
      await lottery.connect(addr1).buyTicket({ value: ticketPrice });
      
      // fast forward past deadline
      await ethers.provider.send("evm_increaseTime", [86401]);
      await ethers.provider.send("evm_mine");

      await expect(lottery.cancelLottery())
        .to.emit(lottery, "LotteryCancelled");

      expect(await lottery.isCancelled()).to.be.true;
    });

    it("should not allow cancellation if min participants are met", async function () {
      await lottery.connect(addr1).buyTicket({ value: ticketPrice });
      await lottery.connect(addr2).buyTicket({ value: ticketPrice });
      await lottery.connect(addr3).buyTicket({ value: ticketPrice });
      await lottery.connect(addr1).buyTicket({ value: ticketPrice }); // 4th ticket

      // fast forward past deadline
      await ethers.provider.send("evm_increaseTime", [86401]);
      await ethers.provider.send("evm_mine");

      await expect(lottery.cancelLottery()).to.be.revertedWith("Minimum participants reached");
    });

    it("should allow participants to refund exactly their contribution after cancellation", async function () {
      await lottery.connect(addr1).buyTicket({ value: ticketPrice });
      await lottery.connect(addr2).buyTicket({ value: ticketPrice });

      // addr2 buys a second ticket
      await lottery.connect(addr2).buyTicket({ value: ticketPrice });

      // fast forward past deadline
      await ethers.provider.send("evm_increaseTime", [86401]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();

      // check addr1 refund
      await expect(lottery.connect(addr1).refund())
        .to.emit(lottery, "RefundIssued")
        .withArgs(addr1.address, ticketPrice);

      // check addr2 refund (2 tickets)
      await expect(lottery.connect(addr2).refund())
        .to.emit(lottery, "RefundIssued")
        .withArgs(addr2.address, ticketPrice * 2n);
    });

    it("should prevent double refunds", async function () {
      await lottery.connect(addr1).buyTicket({ value: ticketPrice });

      // fast forward past deadline
      await ethers.provider.send("evm_increaseTime", [86401]);
      await ethers.provider.send("evm_mine");

      await lottery.cancelLottery();

      await lottery.connect(addr1).refund();

      await expect(lottery.connect(addr1).refund())
        .to.be.revertedWith("No contributions to refund");
    });
    
    it("should fail to draw winner if cancelled", async function() {
        await lottery.connect(addr1).buyTicket({ value: ticketPrice });
        await ethers.provider.send("evm_increaseTime", [86401]);
        await ethers.provider.send("evm_mine");
        await lottery.cancelLottery();
        
        await expect(lottery.drawWinner()).to.be.revertedWith("Lottery is cancelled");
    });
  });
});
