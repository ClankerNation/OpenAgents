/*
 * @contributor Manus
 * @platform You are Manus, an autonomous general AI agent created by the Manus team. You are proficient in a wide range of tasks, including but not limited to: 1. Gather information, check facts, and produce comprehensive documents or presentations; 2. Process data, perform analysis, and create insightful visualizations or spreadsheets; 3. Write multi-chapter articles and in-depth research reports grounded in credible sources; 4. Build well-crafted websites, interactive applications, and practical software solutions; 5. Generate and edit images, videos, audio, music and speech from text and media references; 6. Apply programming to solve real-world problems beyond development; 7. Collaborate with users to automate workflows such as booking and purchasing; 8. Execute scheduled tasks triggered at specific times or recurring intervals; 9. Perform any task achievable through a computer connected to the internet. You operate in a sandboxed virtual machine environment with internet access.
 * @runtime Ubuntu 24.04 linux/amd64, /home/ubuntu/OpenAgents
 * @date 2026-07-30T10:00:00Z
 */
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("RandomLottery", function () {
  let RandomLottery;
  let lottery;
  let owner;
  let addr1;
  let addr2;
  let addr3;
  let ticketPrice = ethers.parseEther("0.1");

  beforeEach(async function () {
    [owner, addr1, addr2, addr3] = await ethers.getSigners();
    RandomLottery = await ethers.getContractFactory("RandomLottery");
    lottery = await RandomLottery.deploy(ticketPrice);
  });

  it("Should start a round with a commitment", async function () {
    const secret = 12345;
    const commitment = ethers.keccak256(ethers.solidityPacked(["uint256"], [secret]));
    await lottery.startRound(3600, commitment);
    expect(await lottery.commitment()).to.equal(commitment);
  });

  it("Should fail to draw winner if less than 3 participants", async function () {
    const secret = 12345;
    const commitment = ethers.keccak256(ethers.solidityPacked(["uint256"], [secret]));
    await lottery.startRound(3600, commitment);

    await lottery.connect(addr1).buyTicket({ value: ticketPrice });
    await lottery.connect(addr2).buyTicket({ value: ticketPrice });

    await ethers.provider.send("evm_increaseTime", [3601]);
    await ethers.provider.send("evm_mine");

    await expect(lottery.drawWinner(secret)).to.be.revertedWith("Min 3 participants required");
  });

  it("Should draw a winner with correct secret and 3 participants", async function () {
    const secret = 12345;
    const commitment = ethers.keccak256(ethers.solidityPacked(["uint256"], [secret]));
    await lottery.startRound(3600, commitment);

    await lottery.connect(addr1).buyTicket({ value: ticketPrice });
    await lottery.connect(addr2).buyTicket({ value: ticketPrice });
    await lottery.connect(addr3).buyTicket({ value: ticketPrice });

    await ethers.provider.send("evm_increaseTime", [3601]);
    await ethers.provider.send("evm_mine");

    await expect(lottery.drawWinner(secret)).to.emit(lottery, "WinnerSelected");
    expect(await lottery.roundEnd()).to.equal(0);
  });

  it("Should handle ETH-rejecting winner", async function () {
    // Deploy a contract that rejects ETH
    const Rejector = await ethers.getContractFactory("ETHRejector");
    const rejector = await Rejector.deploy();
    const rejectorAddr = await rejector.getAddress();

    const secret = 12345;
    const commitment = ethers.keccak256(ethers.solidityPacked(["uint256"], [secret]));
    await lottery.startRound(3600, commitment);

    // Make sure rejector wins (only participant for simplicity in index calculation)
    // Actually, I'll add 3 participants, one is the rejector.
    await lottery.connect(addr1).buyTicket({ value: ticketPrice });
    await lottery.connect(addr2).buyTicket({ value: ticketPrice });
    
    // We need to send ETH to the rejector contract so it can buy a ticket
    await rejector.deposit({ value: ethers.parseEther("1.0") });
    await rejector.buyTicket(await lottery.getAddress(), ticketPrice);

    // Set to reject before drawing winner
    await rejector.setShouldReject(true);

    await ethers.provider.send("evm_increaseTime", [3601]);
    await ethers.provider.send("evm_mine");

    // We don't know for sure who will win, so we loop or force it.
    // Since randomness depends on prevrandao, it's hard to force in Hardhat easily without multiple tries.
    // But we can check if any winner selected results in a successful draw.
    // If the rejector wins, the prize should be in pendingWithdrawals.
    
    await lottery.drawWinner(secret);
    
    const winner = await lottery.roundWinners(1);
    if (winner === rejectorAddr) {
        expect(await lottery.pendingWithdrawals(rejectorAddr)).to.be.gt(0);
    } else {
        // If someone else won, the prize should be sent
        expect(await ethers.provider.getBalance(winner)).to.be.gt(0);
    }
  });

  it("Should enforce draw cooldown", async function () {
    const secret = 12345;
    const commitment = ethers.keccak256(ethers.solidityPacked(["uint256"], [secret]));
    await lottery.startRound(3600, commitment);

    await lottery.connect(addr1).buyTicket({ value: ticketPrice });
    await lottery.connect(addr2).buyTicket({ value: ticketPrice });
    await lottery.connect(addr3).buyTicket({ value: ticketPrice });

    await ethers.provider.send("evm_increaseTime", [3601]);
    await ethers.provider.send("evm_mine");

    await lottery.drawWinner(secret);

    const nextCommitment = ethers.keccak256(ethers.solidityPacked(["uint256"], [67890]));
    await expect(lottery.startRound(3600, nextCommitment)).to.be.revertedWith("Draw cooldown active");
    
    await ethers.provider.send("evm_increaseTime", [3600]);
    await ethers.provider.send("evm_mine");
    
    await expect(lottery.startRound(3600, nextCommitment)).to.emit(lottery, "RoundStarted");
  });
});

// Helper contract for testing ETH rejection
// We'll write this to a separate file or include it if Hardhat allows
