const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PaymentEscrow", function () {
  let token, escrow;
  let owner, payer, payee, other;
  const amount = ethers.parseEther("100");

  beforeEach(async function () {
    [owner, payer, payee, other] = await ethers.getSigners();

    const AgentToken = await ethers.getContractFactory("AgentToken");
    token = await AgentToken.deploy("Agent", "AGENT", ethers.parseEther("1000000"));

    const PaymentEscrow = await ethers.getContractFactory("PaymentEscrow");
    escrow = await PaymentEscrow.deploy();

    await token.transfer(payer.address, amount);
    await token.connect(payer).approve(await escrow.getAddress(), amount);
  });

  async function createEscrow(lockDuration = 0) {
    const tx = await escrow
      .connect(payer)
      .createEscrow(payee.address, await token.getAddress(), amount, lockDuration);
    const receipt = await tx.wait();
    return receipt.logs[1].args.escrowId;
  }

  it("allows either party to dispute", async function () {
    const escrowId = await createEscrow();

    await expect(escrow.connect(payee).dispute(escrowId))
      .to.emit(escrow, "EscrowDisputed")
      .withArgs(escrowId, payee.address);

    const record = await escrow.escrows(escrowId);
    expect(record.disputed).to.equal(true);
  });

  it("lets the owner resolve a dispute with a split", async function () {
    const escrowId = await createEscrow();
    await escrow.connect(payer).dispute(escrowId);

    const payeeAmount = ethers.parseEther("40");
    const payerRefund = ethers.parseEther("60");

    await expect(escrow.resolveDispute(escrowId, payeeAmount, payerRefund))
      .to.emit(escrow, "EscrowResolved")
      .withArgs(escrowId, payeeAmount, payerRefund);

    expect(await token.balanceOf(payee.address)).to.equal(payeeAmount);
    expect(await token.balanceOf(payer.address)).to.equal(payerRefund);
  });

  it("tracks partial releases", async function () {
    const escrowId = await createEscrow();
    const partialAmount = ethers.parseEther("25");

    await escrow.connect(payer).releasePartial(escrowId, partialAmount);

    const record = await escrow.escrows(escrowId);
    expect(record.remainingAmount).to.equal(amount - partialAmount);
    expect(record.released).to.equal(false);
    expect(await token.balanceOf(payee.address)).to.equal(partialAmount);
  });

  it("auto-refunds remaining funds after the timeout", async function () {
    const escrowId = await createEscrow(1);

    await ethers.provider.send("evm_increaseTime", [30 * 24 * 60 * 60 + 2]);
    await ethers.provider.send("evm_mine");

    await expect(escrow.connect(payer).refundEscrow(escrowId))
      .to.emit(escrow, "EscrowRefunded")
      .withArgs(escrowId, payer.address, amount);

    const record = await escrow.escrows(escrowId);
    expect(record.refunded).to.equal(true);
    expect(record.remainingAmount).to.equal(0);
  });

  it("rejects non-party disputes", async function () {
    const escrowId = await createEscrow();

    await expect(escrow.connect(other).dispute(escrowId)).to.be.revertedWith("Not party");
  });
});
