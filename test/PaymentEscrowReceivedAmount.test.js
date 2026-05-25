const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PaymentEscrow received amount accounting", function () {
  let payer;
  let payee;
  let escrow;
  let normalToken;
  let feeToken;

  const initialSupply = ethers.parseEther("1000000");
  const escrowAmount = ethers.parseEther("100");

  beforeEach(async function () {
    [payer, payee] = await ethers.getSigners();

    const PaymentEscrow = await ethers.getContractFactory("PaymentEscrow");
    escrow = await PaymentEscrow.deploy();

    const AgentToken = await ethers.getContractFactory("AgentToken");
    normalToken = await AgentToken.deploy("Normal", "NORM", initialSupply);

    const FeeOnTransferToken = await ethers.getContractFactory("FeeOnTransferToken");
    feeToken = await FeeOnTransferToken.deploy("Fee", "FEE", initialSupply, 1_000);
  });

  it("rejects zero amount escrows", async function () {
    await normalToken.approve(await escrow.getAddress(), escrowAmount);

    await expect(
      escrow.createEscrow(payee.address, await normalToken.getAddress(), 0, 0),
    ).to.be.revertedWith("Amount must be > 0");
  });

  it("stores the exact received amount for normal ERC20 tokens", async function () {
    await normalToken.approve(await escrow.getAddress(), escrowAmount);

    await expect(
      escrow.createEscrow(payee.address, await normalToken.getAddress(), escrowAmount, 0),
    )
      .to.emit(escrow, "EscrowCreated")
      .withArgs(0, payer.address, escrowAmount);

    const created = await escrow.escrows(0);
    expect(created.amount).to.equal(escrowAmount);
    expect(await normalToken.balanceOf(await escrow.getAddress())).to.equal(escrowAmount);
  });

  it("stores the actual received amount for fee-on-transfer tokens", async function () {
    const expectedReceived = (escrowAmount * 9_000n) / 10_000n;
    await feeToken.approve(await escrow.getAddress(), escrowAmount);

    await expect(
      escrow.createEscrow(payee.address, await feeToken.getAddress(), escrowAmount, 0),
    )
      .to.emit(escrow, "EscrowCreated")
      .withArgs(0, payer.address, expectedReceived);

    const created = await escrow.escrows(0);
    expect(created.amount).to.equal(expectedReceived);
    expect(await feeToken.balanceOf(await escrow.getAddress())).to.equal(expectedReceived);
  });
});
