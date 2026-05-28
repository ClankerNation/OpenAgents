const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PaymentEscrow", function () {
  let escrow, token, feeToken;
  let owner, payer, payee;

  beforeEach(async function () {
    [owner, payer, payee] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("StakingToken");
    token = await Token.deploy();
    await token.deployed();

    const FeeToken = await ethers.getContractFactory("FeeOnTransferToken");
    feeToken = await FeeToken.deploy();
    await feeToken.deployed();

    const Escrow = await ethers.getContractFactory("PaymentEscrow");
    escrow = await Escrow.deploy();
    await escrow.deployed();

    await token.mint(payer.address, ethers.utils.parseEther("1000"));
    await feeToken.mint(payer.address, ethers.utils.parseEther("1000"));
  });

  it("should reject zero amount", async function () {
    await expect(
      escrow.connect(payer).createEscrow(payee.address, token.address, 0, 3600)
    ).to.be.revertedWith("Amount must be > 0");
  });

  it("should create escrow with correct amount", async function () {
    const amount = ethers.utils.parseEther("100");
    await token.connect(payer).approve(escrow.address, amount);
    await escrow.connect(payer).createEscrow(payee.address, token.address, amount, 3600);

    const escrowData = await escrow.escrows(0);
    expect(escrowData.amount).to.equal(amount);
    expect(escrowData.payer).to.equal(payer.address);
    expect(escrowData.payee).to.equal(payee.address);
  });

  it("should handle fee-on-transfer tokens correctly", async function () {
    const amount = ethers.utils.parseEther("100");
    await feeToken.connect(payer).approve(escrow.address, amount);
    await escrow.connect(payer).createEscrow(payee.address, feeToken.address, amount, 3600);

    const escrowData = await escrow.escrows(0);
    // Fee-on-transfer token charges 1% fee, so actual received = 99
    const expectedAmount = ethers.utils.parseEther("99");
    expect(escrowData.amount).to.equal(expectedAmount);
  });

  it("should release escrow to payee", async function () {
    const amount = ethers.utils.parseEther("100");
    await token.connect(payer).approve(escrow.address, amount);
    await escrow.connect(payer).createEscrow(payee.address, token.address, amount, 3600);

    const payeeBalanceBefore = await token.balanceOf(payee.address);
    await escrow.connect(payer).releaseEscrow(0);
    const payeeBalanceAfter = await token.balanceOf(payee.address);

    expect(payeeBalanceAfter.sub(payeeBalanceBefore)).to.equal(amount);
  });

  it("should refund escrow after lock expires", async function () {
    const amount = ethers.utils.parseEther("100");
    await token.connect(payer).approve(escrow.address, amount);
    await escrow.connect(payer).createEscrow(payee.address, token.address, amount, 0);

    const payerBalanceBefore = await token.balanceOf(payer.address);
    await escrow.connect(payer).refundEscrow(0);
    const payerBalanceAfter = await token.balanceOf(payer.address);

    expect(payerBalanceAfter.sub(payerBalanceBefore)).to.equal(amount);
  });
});
