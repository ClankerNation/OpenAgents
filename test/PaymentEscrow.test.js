const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PaymentEscrow", function () {
  let escrow, mockToken, feeToken;
  let payer, payee, other;
  const LOCK_DURATION = 86400; // 1 day
  const FEE_BPS = 500n; // 5%
  const ONE_E18 = 10n ** 18n;

  beforeEach(async function () {
    [payer, payee, other] = await ethers.getSigners();

    const MockERC20 = await ethers.getContractFactory("MockERC20");
    mockToken = await MockERC20.deploy("Mock", "MCK");
    await mockToken.waitForDeployment();

    const FeeOnTransferToken = await ethers.getContractFactory("FeeOnTransferToken");
    feeToken = await FeeOnTransferToken.deploy("Fee", "FEE");
    await feeToken.waitForDeployment();

    const PaymentEscrow = await ethers.getContractFactory("PaymentEscrow");
    escrow = await PaymentEscrow.deploy();
    await escrow.waitForDeployment();

    // Fund payer with both tokens
    await mockToken.transfer(payer.address, ONE_E18 * 1000n);
    await feeToken.transfer(payer.address, ONE_E18 * 1000n);

    // Approve escrow contract
    await mockToken.connect(payer).approve(escrow.target, ethers.MaxUint256);
    await feeToken.connect(payer).approve(escrow.target, ethers.MaxUint256);
  });

  describe("createEscrow", function () {
    it("should reject zero amount", async function () {
      await expect(
        escrow.connect(payer).createEscrow(payee.address, mockToken.target, 0, LOCK_DURATION)
      ).to.be.revertedWith("Amount must be > 0");
    });

    it("should reject invalid payee", async function () {
      await expect(
        escrow.connect(payer).createEscrow(ethers.ZeroAddress, mockToken.target, ONE_E18 * 100n, LOCK_DURATION)
      ).to.be.revertedWith("Invalid payee");
    });

    it("should reject invalid token", async function () {
      await expect(
        escrow.connect(payer).createEscrow(payee.address, ethers.ZeroAddress, ONE_E18 * 100n, LOCK_DURATION)
      ).to.be.revertedWith("Invalid token");
    });

    it("should create escrow with standard ERC20 and store correct amount", async function () {
      const amount = ONE_E18 * 100n;
      const tx = await escrow.connect(payer).createEscrow(
        payee.address, mockToken.target, amount, LOCK_DURATION
      );

      await expect(tx)
        .to.emit(escrow, "EscrowCreated")
        .withArgs(0, payer.address, amount);

      const escrowData = await escrow.escrows(0);
      expect(escrowData.payer).to.equal(payer.address);
      expect(escrowData.payee).to.equal(payee.address);
      expect(escrowData.token).to.equal(mockToken.target);
      expect(escrowData.amount).to.equal(amount);
      expect(escrowData.released).to.be.false;
      expect(escrowData.refunded).to.be.false;
    });

    it("should store actual received amount for fee-on-transfer tokens", async function () {
      const nominalAmount = ONE_E18 * 100n;
      const expectedReceived = nominalAmount - (nominalAmount * FEE_BPS) / 10000n;

      const tx = await escrow.connect(payer).createEscrow(
        payee.address, feeToken.target, nominalAmount, LOCK_DURATION
      );

      await expect(tx)
        .to.emit(escrow, "EscrowCreated")
        .withArgs(0, payer.address, expectedReceived);

      const escrowData = await escrow.escrows(0);
      expect(escrowData.amount).to.equal(expectedReceived);

      const balance = await feeToken.balanceOf(escrow.target);
      expect(balance).to.equal(expectedReceived);
    });

    it("should increment escrowCount", async function () {
      await escrow.connect(payer).createEscrow(
        payee.address, mockToken.target, ONE_E18 * 10n, LOCK_DURATION
      );
      expect(await escrow.escrowCount()).to.equal(1n);

      await escrow.connect(payer).createEscrow(
        payee.address, mockToken.target, ONE_E18 * 20n, LOCK_DURATION
      );
      expect(await escrow.escrowCount()).to.equal(2n);
    });
  });

  describe("releaseEscrow", function () {
    it("should release to payee", async function () {
      const amount = ONE_E18 * 50n;
      await escrow.connect(payer).createEscrow(
        payee.address, mockToken.target, amount, LOCK_DURATION
      );

      await expect(escrow.connect(payer).releaseEscrow(0))
        .to.emit(escrow, "EscrowReleased")
        .withArgs(0, payee.address, amount);

      const escrowData = await escrow.escrows(0);
      expect(escrowData.released).to.be.true;
    });

    it("should reject release from non-payer non-owner", async function () {
      const amount = ONE_E18 * 50n;
      await escrow.connect(payer).createEscrow(
        payee.address, mockToken.target, amount, LOCK_DURATION
      );

      await expect(escrow.connect(other).releaseEscrow(0))
        .to.be.revertedWith("Not authorized");
    });

    it("should reject double release", async function () {
      await escrow.connect(payer).createEscrow(
        payee.address, mockToken.target, ONE_E18 * 10n, LOCK_DURATION
      );
      await escrow.connect(payer).releaseEscrow(0);
      await expect(escrow.connect(payer).releaseEscrow(0))
        .to.be.revertedWith("Already settled");
    });
  });

  describe("refundEscrow", function () {
    it("should refund to payer after lock expires", async function () {
      const amount = ONE_E18 * 30n;
      await escrow.connect(payer).createEscrow(
        payee.address, mockToken.target, amount, LOCK_DURATION
      );

      await ethers.provider.send("evm_increaseTime", [LOCK_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await expect(escrow.connect(payer).refundEscrow(0))
        .to.emit(escrow, "EscrowRefunded")
        .withArgs(0, payer.address, amount);
    });

    it("should reject refund before lock expires", async function () {
      await escrow.connect(payer).createEscrow(
        payee.address, mockToken.target, ONE_E18 * 10n, LOCK_DURATION
      );

      await expect(escrow.connect(payer).refundEscrow(0))
        .to.be.revertedWith("Lock not expired");
    });

    it("should reject refund from non-payer", async function () {
      await escrow.connect(payer).createEscrow(
        payee.address, mockToken.target, ONE_E18 * 10n, LOCK_DURATION
      );

      await ethers.provider.send("evm_increaseTime", [LOCK_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      await expect(escrow.connect(other).refundEscrow(0))
        .to.be.revertedWith("Not payer");
    });
  });

  describe("fee-on-transfer lifecycle", function () {
    it("should release correct actual amount for fee-on-transfer tokens", async function () {
      const nominalAmount = ONE_E18 * 200n;
      const storedAmount = nominalAmount - (nominalAmount * FEE_BPS) / 10000n;

      await escrow.connect(payer).createEscrow(
        payee.address, feeToken.target, nominalAmount, LOCK_DURATION
      );

      const payeeBefore = await feeToken.balanceOf(payee.address);
      await escrow.connect(payer).releaseEscrow(0);
      const payeeAfter = await feeToken.balanceOf(payee.address);

      // Fee-on-transfer applies again on release: payee gets storedAmount - 5%
      const expectedPayee = storedAmount - (storedAmount * FEE_BPS) / 10000n;
      expect(payeeAfter - payeeBefore).to.equal(expectedPayee);
    });

    it("should refund correct actual amount for fee-on-transfer tokens", async function () {
      const nominalAmount = ONE_E18 * 200n;
      const storedAmount = nominalAmount - (nominalAmount * FEE_BPS) / 10000n;

      await escrow.connect(payer).createEscrow(
        payee.address, feeToken.target, nominalAmount, LOCK_DURATION
      );

      await ethers.provider.send("evm_increaseTime", [LOCK_DURATION + 1]);
      await ethers.provider.send("evm_mine");

      const payerBefore = await feeToken.balanceOf(payer.address);
      await escrow.connect(payer).refundEscrow(0);
      const payerAfter = await feeToken.balanceOf(payer.address);

      // Fee-on-transfer applies again on refund
      const expectedRefund = storedAmount - (storedAmount * FEE_BPS) / 10000n;
      expect(payerAfter - payerBefore).to.equal(expectedRefund);
    });
  });
});
