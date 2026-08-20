/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PaymentEscrow Dispute Resolution and Timeout", function () {
  let escrow, token;
  let owner, payer, payee;

  before(async function () {
    [owner, payer, payee] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("AgentToken");
    token = await Token.deploy("Test Token", "TT", ethers.parseEther("1000000"));
    await token.waitForDeployment();

    const Escrow = await ethers.getContractFactory("PaymentEscrow");
    escrow = await Escrow.deploy();
    await escrow.waitForDeployment();

    await token.transfer(payer.address, ethers.parseEther("1000"));
    await token.connect(payer).approve(escrow.target, ethers.MaxUint256);
  });

  it("should allow either party to dispute the escrow", async function () {
    const amount = ethers.parseEther("100");
    const tx = await escrow.connect(payer).createEscrow(payee.address, token.target, amount, 3600);
    const receipt = await tx.wait();
    const escrowId = 0n;

    await expect(
      escrow.connect(payee).dispute(escrowId)
    ).to.emit(escrow, "EscrowDisputed").withArgs(escrowId, payee.address);

    const state = await escrow.escrows(escrowId);
    expect(state.disputed).to.be.true;
  });

  it("should allow owner to resolve dispute with split", async function () {
    const escrowId = 0n;
    const payerShare = ethers.parseEther("40");
    const payeeShare = ethers.parseEther("60");

    await expect(
      escrow.connect(owner).resolveDispute(escrowId, payerShare, payeeShare)
    ).to.emit(escrow, "EscrowResolved").withArgs(escrowId, payerShare, payeeShare);

    const payerBal = await token.balanceOf(payer.address);
    const payeeBal = await token.balanceOf(payee.address);
    
    // Initial was 1000, deposited 100, got 40 back -> 940
    expect(payerBal).to.equal(ethers.parseEther("940"));
    expect(payeeBal).to.equal(payeeShare);
  });

  it("should auto-refund after 30-day timeout on disputed escrow", async function () {
    const amount = ethers.parseEther("50");
    const tx = await escrow.connect(payer).createEscrow(payee.address, token.target, amount, 3600);
    const escrowId = 1n;

    await escrow.connect(payer).dispute(escrowId);

    // Try timeout before 30 days - should revert
    await expect(
      escrow.timeoutRefund(escrowId)
    ).to.be.revertedWith("Timeout not reached");

    // Advance time by 31 days
    await ethers.provider.send("evm_increaseTime", [31 * 24 * 60 * 60]);
    await ethers.provider.send("evm_mine");

    const balBefore = await token.balanceOf(payer.address);
    await escrow.timeoutRefund(escrowId);
    const balAfter = await token.balanceOf(payer.address);

    expect(balAfter - balBefore).to.equal(amount);
  });

  it("should allow partial release", async function () {
    const amount = ethers.parseEther("100");
    const tx = await escrow.connect(payer).createEscrow(payee.address, token.target, amount, 3600);
    const escrowId = 2n;

    const partial = ethers.parseEther("30");
    await escrow.connect(payer).partialRelease(escrowId, partial);

    const state = await escrow.escrows(escrowId);
    expect(state.amount).to.equal(ethers.parseEther("70"));
    expect(state.released).to.be.false;
  });
});
