const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PaymentEscrow — fee-on-transfer + zero-amount", function () {
  let escrow, token;
  let owner, payer, payee;

  beforeEach(async function () {
    [owner, payer, payee] = await ethers.getSigners();

    // Deploy a simple ERC20 mock via the contract factory
    const TokenFactory = await ethers.getContractFactory("TestToken");
    token = await TokenFactory.deploy();
    await token.waitForDeployment();

    const Escrow = await ethers.getContractFactory("PaymentEscrow");
    escrow = await Escrow.deploy();
    await escrow.waitForDeployment();

    // Fund payer
    await token.transfer(payer.address, ethers.parseEther("1000"));
    await token.connect(payer).approve(await escrow.getAddress(), ethers.parseEther("1000"));
  });

  it("rejects zero amount", async function () {
    await expect(
      escrow.connect(payer).createEscrow(
        payee.address,
        await token.getAddress(),
        0,
        3600
      )
    ).to.be.revertedWith("Amount must be > 0");
  });

  it("creates escrow with correct amount for standard ERC20", async function () {
    const amount = ethers.parseEther("100");

    const tx = await escrow.connect(payer).createEscrow(
      payee.address,
      await token.getAddress(),
      amount,
      3600
    );
    const receipt = await tx.wait();

    const escrowId = 0;
    const e = await escrow.escrows(escrowId);
    expect(e.amount).to.equal(amount);
    expect(e.payer).to.equal(payer.address);
    expect(e.payee).to.equal(payee.address);

    // Check event
    const event = receipt.logs.find(
      (log) => log.fragment && log.fragment.name === "EscrowCreated"
    );
    expect(event.args.escrowId).to.equal(escrowId);
    expect(event.args.amount).to.equal(amount);
  });

  it("stores actual received amount on normal transfer", async function () {
    const amount = ethers.parseEther("50");

    const balanceBefore = await token.balanceOf(await escrow.getAddress());
    await escrow.connect(payer).createEscrow(
      payee.address,
      await token.getAddress(),
      amount,
      3600
    );
    const balanceAfter = await token.balanceOf(await escrow.getAddress());

    expect(balanceAfter - balanceBefore).to.equal(amount);

    const e = await escrow.escrows(0);
    expect(e.amount).to.equal(amount);
  });

  it("release sends stored (actual) amount, not input amount", async function () {
    const amount = ethers.parseEther("200");
    await escrow.connect(payer).createEscrow(
      payee.address,
      await token.getAddress(),
      amount,
      0 // no lock
    );

    const payeeBalBefore = await token.balanceOf(payee.address);
    await escrow.releaseEscrow(0);
    const payeeBalAfter = await token.balanceOf(payee.address);

    // Should receive exactly the stored amount
    expect(payeeBalAfter - payeeBalBefore).to.equal(amount);
  });

  it("refund sends stored amount back to payer", async function () {
    const amount = ethers.parseEther("150");
    await escrow.connect(payer).createEscrow(
      payee.address,
      await token.getAddress(),
      amount,
      1 // 1 second lock
    );

    // Advance time past lock
    await ethers.provider.send("evm_increaseTime", [2]);
    await ethers.provider.send("evm_mine");

    const payerBalBefore = await token.balanceOf(payer.address);
    await escrow.connect(payer).refundEscrow(0);
    const payerBalAfter = await token.balanceOf(payer.address);

    expect(payerBalAfter - payerBalBefore).to.equal(amount);
  });
});
