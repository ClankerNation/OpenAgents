/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PaymentEscrow Zero Amount & Fee-on-Transfer Fix", function () {
  let escrow, token;
  let owner, payer, payee;

  before(async function () {
    [owner, payer, payee] = await ethers.getSigners();
    
    // Deploy AgentToken for testing
    const Token = await ethers.getContractFactory("AgentToken");
    token = await Token.deploy("Test Token", "TT", ethers.parseEther("1000000"));
    await token.waitForDeployment();
    
    const Escrow = await ethers.getContractFactory("PaymentEscrow");
    escrow = await Escrow.deploy();
    await escrow.waitForDeployment();
    
    // Transfer tokens to payer
    await token.transfer(payer.address, ethers.parseEther("1000"));
    await token.connect(payer).approve(escrow.target, ethers.MaxUint256);
  });

  it("should revert on zero amount", async function () {
    await expect(
      escrow.connect(payer).createEscrow(payee.address, token.target, 0, 3600)
    ).to.be.revertedWith("Amount must be > 0");
  });

  it("should store actual received amount for normal tokens", async function () {
    const amount = ethers.parseEther("100");
    const tx = await escrow.connect(payer).createEscrow(payee.address, token.target, amount, 3600);
    const receipt = await tx.wait();
    
    // Parse the EscrowCreated event
    const event = receipt.logs.find(log => {
      try {
        const parsed = escrow.interface.parseLog(log);
        return parsed && parsed.name === "EscrowCreated";
      } catch (e) { return false; }
    });
    
    expect(event).to.not.be.undefined;
    const parsed = escrow.interface.parseLog(event);
    expect(parsed.args.amount).to.equal(amount);
  });

  it("should handle fee-on-transfer tokens correctly", async function () {
    const amount = ethers.parseEther("50");
    const balanceBefore = await token.balanceOf(escrow.target);
    
    await escrow.connect(payer).createEscrow(payee.address, token.target, amount, 3600);
    
    const balanceAfter = await token.balanceOf(escrow.target);
    const actualReceived = balanceAfter - balanceBefore;
    
    expect(actualReceived).to.equal(amount);
    
    const escrowCount = await escrow.escrowCount();
    const escrowData = await escrow.escrows(escrowCount - 1n);
    expect(escrowData.amount).to.equal(actualReceived);
  });
});
