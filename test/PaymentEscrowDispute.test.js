const { expect } = require("chai");
const { ethers, network } = require("hardhat");

describe("PaymentEscrow dispute and timeout flows", function () {
  async function deployFixture() {
    const [owner, payer, payee, stranger] = await ethers.getSigners();
    const Token = await ethers.getContractFactory("MockERC20");
    const token = await Token.deploy("Mock Token", "MOCK");
    await token.waitForDeployment();

    const PaymentEscrow = await ethers.getContractFactory("PaymentEscrowHarness");
    const escrow = await PaymentEscrow.deploy();
    await escrow.waitForDeployment();

    return { owner, payer, payee, stranger, token, escrow };
  }

  async function createEscrow(token, escrow, payer, payee, amount = 1000n, lockDuration = 60n) {
    const escrowAddress = await escrow.getAddress();
    await token.mint(payer.address, amount);
    await token.connect(payer).approve(escrowAddress, amount);
    await escrow.connect(payer).createEscrow(payee.address, await token.getAddress(), amount, lockDuration);
  }

  it("allows either escrow party to dispute and blocks strangers", async function () {
    const { payer, payee, stranger, token, escrow } = await deployFixture();
    await createEscrow(token, escrow, payer, payee);

    await expect(escrow.connect(stranger).dispute(0)).to.be.revertedWith("Not party");
    await expect(escrow.connect(payee).dispute(0))
      .to.emit(escrow, "EscrowDisputed")
      .withArgs(0, payee.address);

    const stored = await escrow.escrows(0);
    expect(stored.disputed).to.equal(true);
    await expect(escrow.connect(payer).releaseEscrow(0)).to.be.revertedWith("Under dispute");
  });

  it("lets the owner resolve a dispute by splitting remaining funds", async function () {
    const { owner, payer, payee, token, escrow } = await deployFixture();
    await createEscrow(token, escrow, payer, payee);

    await escrow.connect(payer).dispute(0);
    await expect(escrow.connect(owner).resolveDispute(0, 400n, 600n))
      .to.emit(escrow, "DisputeResolved")
      .withArgs(0, 400n, 600n);

    expect(await token.balanceOf(payer.address)).to.equal(400n);
    expect(await token.balanceOf(payee.address)).to.equal(600n);
    expect(await escrow.remainingAmount(0)).to.equal(0);

    const stored = await escrow.escrows(0);
    expect(stored.released).to.equal(true);
    expect(stored.refunded).to.equal(true);
    expect(stored.releasedAmount).to.equal(600n);
    expect(stored.refundedAmount).to.equal(400n);
  });

  it("auto-refunds remaining funds after the 30 day timeout", async function () {
    const { payer, payee, token, escrow } = await deployFixture();
    await createEscrow(token, escrow, payer, payee, 1000n, 60n);

    await network.provider.send("evm_increaseTime", [60 + 30 * 24 * 60 * 60 + 1]);
    await network.provider.send("evm_mine");

    await expect(escrow.connect(payee).refundExpiredEscrow(0))
      .to.emit(escrow, "EscrowRefunded")
      .withArgs(0, payer.address, 1000n);
    expect(await token.balanceOf(payer.address)).to.equal(1000n);
  });

  it("tracks partial releases and prevents over-release", async function () {
    const { payer, payee, token, escrow } = await deployFixture();
    await createEscrow(token, escrow, payer, payee);

    await expect(escrow.connect(payer)["releaseEscrow(uint256,uint256)"](0, 250n))
      .to.emit(escrow, "EscrowReleased")
      .withArgs(0, payee.address, 250n);

    expect(await escrow.remainingAmount(0)).to.equal(750n);
    let stored = await escrow.escrows(0);
    expect(stored.released).to.equal(false);
    expect(stored.releasedAmount).to.equal(250n);

    await expect(escrow.connect(payer)["releaseEscrow(uint256,uint256)"](0, 751n)).to.be.revertedWith(
      "Invalid release amount"
    );

    await escrow.connect(payer).releaseEscrow(0);
    expect(await token.balanceOf(payee.address)).to.equal(1000n);
    expect(await escrow.remainingAmount(0)).to.equal(0);
    stored = await escrow.escrows(0);
    expect(stored.released).to.equal(true);
    expect(stored.releasedAmount).to.equal(1000n);
  });
});
