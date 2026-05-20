const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PaymentEscrow", function () {
  async function deployFixture(feeBps = 0) {
    const [owner, payer, payee] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("MockFeeOnTransferToken");
    const token = await Token.deploy("Mock Token", "MOCK", feeBps);
    await token.waitForDeployment();

    const PaymentEscrow = await ethers.getContractFactory("PaymentEscrowHarness");
    const escrow = await PaymentEscrow.deploy();
    await escrow.waitForDeployment();

    return { owner, payer, payee, token, escrow };
  }

  it("rejects zero amount escrows", async function () {
    const { payer, payee, token, escrow } = await deployFixture();

    await expect(
      escrow.connect(payer).createEscrow(payee.address, await token.getAddress(), 0, 0)
    ).to.be.revertedWith("Amount must be > 0");
  });

  it("stores and releases the full amount for normal ERC20 tokens", async function () {
    const { payer, payee, token, escrow } = await deployFixture();
    const amount = ethers.parseEther("100");
    const escrowAddress = await escrow.getAddress();

    await token.mint(payer.address, amount);
    await token.connect(payer).approve(escrowAddress, amount);

    await expect(escrow.connect(payer).createEscrow(payee.address, await token.getAddress(), amount, 0))
      .to.emit(escrow, "EscrowCreated")
      .withArgs(0, payer.address, amount);

    const stored = await escrow.escrows(0);
    expect(stored.amount).to.equal(amount);
    expect(await token.balanceOf(escrowAddress)).to.equal(amount);

    await escrow.connect(payer).releaseEscrow(0);
    expect(await token.balanceOf(payee.address)).to.equal(amount);
    expect(await token.balanceOf(escrowAddress)).to.equal(0);
  });

  it("stores the actual received amount for fee-on-transfer tokens", async function () {
    const { payer, payee, token, escrow } = await deployFixture(1_000);
    const amount = ethers.parseEther("100");
    const received = ethers.parseEther("90");
    const receivedAfterReleaseFee = ethers.parseEther("81");
    const escrowAddress = await escrow.getAddress();

    await token.mint(payer.address, amount);
    await token.connect(payer).approve(escrowAddress, amount);

    await expect(escrow.connect(payer).createEscrow(payee.address, await token.getAddress(), amount, 0))
      .to.emit(escrow, "EscrowCreated")
      .withArgs(0, payer.address, received);

    const stored = await escrow.escrows(0);
    expect(stored.amount).to.equal(received);
    expect(await token.balanceOf(escrowAddress)).to.equal(received);

    await escrow.connect(payer).releaseEscrow(0);
    expect(await token.balanceOf(escrowAddress)).to.equal(0);
    expect(await token.balanceOf(payee.address)).to.equal(receivedAfterReleaseFee);
  });
});
