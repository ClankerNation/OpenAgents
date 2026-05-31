const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PaymentEscrow", function () {
  let escrow;
  let payer;
  let payee;
  let feeCollector;

  beforeEach(async function () {
    [, payer, payee, feeCollector] = await ethers.getSigners();
    const PaymentEscrow = await ethers.getContractFactory("PaymentEscrow");
    escrow = await PaymentEscrow.deploy();
    await escrow.waitForDeployment();
  });

  async function deployToken(feeBps) {
    const Token = await ethers.getContractFactory("MockFeeOnTransferToken");
    const token = await Token.deploy("Mock", "MOCK", feeBps, feeCollector.address);
    await token.waitForDeployment();
    return token;
  }

  it("rejects zero amount", async function () {
    const token = await deployToken(0);
    await token.mint(payer.address, 1000n);
    await token.connect(payer).approve(escrow.target, 1000n);

    await expect(
      escrow.connect(payer).createEscrow(payee.address, token.target, 0n, 0)
    ).to.be.revertedWith("Amount must be > 0");
  });

  it("stores full amount for standard ERC20", async function () {
    const token = await deployToken(0);
    const amount = ethers.parseUnits("100", 18);

    await token.mint(payer.address, amount);
    await token.connect(payer).approve(escrow.target, amount);

    await expect(
      escrow.connect(payer).createEscrow(payee.address, token.target, amount, 3600)
    )
      .to.emit(escrow, "EscrowCreated")
      .withArgs(0n, payer.address, amount);

    const stored = await escrow.escrows(0n);
    expect(stored.amount).to.equal(amount);
    expect(await token.balanceOf(escrow.target)).to.equal(amount);
  });

  it("stores actual received amount for fee-on-transfer token", async function () {
    const token = await deployToken(500); // 5%
    const amount = ethers.parseUnits("100", 18);
    const expectedReceived = (amount * 9500n) / 10000n;

    await token.mint(payer.address, amount);
    await token.connect(payer).approve(escrow.target, amount);

    await expect(
      escrow.connect(payer).createEscrow(payee.address, token.target, amount, 3600)
    )
      .to.emit(escrow, "EscrowCreated")
      .withArgs(0n, payer.address, expectedReceived);

    const stored = await escrow.escrows(0n);
    expect(stored.amount).to.equal(expectedReceived);
    expect(await token.balanceOf(escrow.target)).to.equal(expectedReceived);
  });
});
