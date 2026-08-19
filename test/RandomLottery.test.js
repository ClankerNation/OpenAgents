const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("RandomLottery Refund Mechanism", function () {
    let lottery;
    let owner, player1, player2;
    const TICKET_PRICE = ethers.parseEther("0.1");
    const MIN_PARTICIPANTS = 3;

    beforeEach(async function () {
        [owner, player1, player2] = await ethers.getSigners();
        const Factory = await ethers.getContractFactory("RandomLottery");
        lottery = await Factory.deploy(TICKET_PRICE, MIN_PARTICIPANTS);
        await lottery.waitForDeployment();
        
        // Start a round with 1 day duration
        await lottery.connect(owner).startRound(86400);
    });

    it("should allow cancellation if not enough participants after deadline", async function () {
        // Only 2 players buy tickets (min is 3)
        await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
        await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });

        // Advance time past deadline
        await ethers.provider.send("evm_increaseTime", [86401]);
        await ethers.provider.send("evm_mine");

        await expect(lottery.connect(owner).cancelLottery())
            .to.emit(lottery, "LotteryCancelled");
    });

    it("should allow participants to refund after cancellation", async function () {
        await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
        await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });

        await ethers.provider.send("evm_increaseTime", [86401]);
        await ethers.provider.send("evm_mine");

        await lottery.connect(owner).cancelLottery();

        await expect(lottery.connect(player1).refund())
            .to.changeEtherBalance(player1, TICKET_PRICE);
            
        await expect(lottery.connect(player2).refund())
            .to.changeEtherBalance(player2, TICKET_PRICE);
    });

    it("should prevent double refunds", async function () {
        await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });

        await ethers.provider.send("evm_increaseTime", [86401]);
        await ethers.provider.send("evm_mine");

        await lottery.connect(owner).cancelLottery();
        await lottery.connect(player1).refund();

        await expect(lottery.connect(player1).refund())
            .to.be.revertedWith("Already refunded");
    });

    it("should prevent refunds on active lotteries", async function () {
        await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });

        await expect(lottery.connect(player1).refund())
            .to.be.revertedWith("Lottery not cancelled");
    });
    
    it("should prevent cancellation if enough participants", async function () {
        const [, , , p3] = await ethers.getSigners();
        await lottery.connect(player1).buyTicket({ value: TICKET_PRICE });
        await lottery.connect(player2).buyTicket({ value: TICKET_PRICE });
        await lottery.connect(p3).buyTicket({ value: TICKET_PRICE });

        await ethers.provider.send("evm_increaseTime", [86401]);
        await ethers.provider.send("evm_mine");

        await expect(lottery.connect(owner).cancelLottery())
            .to.be.revertedWith("Enough participants");
    });
});
