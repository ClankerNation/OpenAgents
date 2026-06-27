const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PaymentEscrow", function () {
  let paymentEscrow, mockToken, feeToken;
  let owner, payer, payee;

  beforeEach(async function () {
    [owner, payer, payee] = await ethers.getSigners();

    const PaymentEscrow = await ethers.getContractFactory("PaymentEscrow");
    paymentEscrow = await PaymentEscrow.deploy();
    await paymentEscrow.waitForDeployment();

    const MockERC20 = await ethers.getContractFactory("MockERC20");
    mockToken = await MockERC20.deploy("Mock Token", "MTK");
    await mockToken.waitForDeployment();

    const FeeOnTransferToken = await ethers.getContractFactory("FeeOnTransferToken");
    feeToken = await FeeOnTransferToken.deploy("Fee Token", "FTK", 5);
    await feeToken.waitForDeployment();

    await mockToken.mint(payer.address, ethers.parseEther("1000"));
    await feeToken.mint(payer.address, ethers.parseEther("1000"));
  });

  describe("createEscrow", function () {
    it("should reject zero amount", async function () {
      await mockToken.connect(payer).approve(await paymentEscrow.getAddress(), ethers.parseEther("100"));
      await expect(
        paymentEscrow.connect(payer).createEscrow(
          payee.address,
          await mockToken.getAddress(),
          0,
          3600
        )
      ).to.be.revertedWith("Amount must be > 0");
    });

    it("should reject zero payee address", async function () {
      await mockToken.connect(payer).approve(await paymentEscrow.getAddress(), ethers.parseEther("100"));
      await expect(
        paymentEscrow.connect(payer).createEscrow(
          ethers.ZeroAddress,
          await mockToken.getAddress(),
          ethers.parseEther("100"),
          3600
        )
      ).to.be.revertedWith("Invalid payee");
    });

    it("should create escrow with normal ERC20 token", async function () {
      const amount = ethers.parseEther("100");
      await mockToken.connect(payer).approve(await paymentEscrow.getAddress(), amount);

      await paymentEscrow.connect(payer).createEscrow(
        payee.address,
        await mockToken.getAddress(),
        amount,
        3600
      );

      const escrow = await paymentEscrow.escrows(0);
      expect(escrow.payer).to.equal(payer.address);
      expect(escrow.payee).to.equal(payee.address);
      expect(escrow.amount).to.equal(amount);
      expect(escrow.released).to.be.false;
      expect(escrow.refunded).to.be.false;
    });

    it("should handle fee-on-transfer tokens correctly", async function () {
      const amount = ethers.parseEther("100");
      await feeToken.connect(payer).approve(await paymentEscrow.getAddress(), amount);

      await paymentEscrow.connect(payer).createEscrow(
        payee.address,
        await feeToken.getAddress(),
        amount,
        3600
      );

      const escrow = await paymentEscrow.escrows(0);
      const expectedFee = (amount * 5n) / 100n;
      const expectedActual = amount - expectedFee;
      expect(escrow.amount).to.equal(expectedActual);

      const contractBalance = await feeToken.balanceOf(await paymentEscrow.getAddress());
      expect(contractBalance).to.equal(expectedActual);
    });

    it("should emit EscrowCreated event", async function () {
      const amount = ethers.parseEther("100");
      await mockToken.connect(payer).approve(await paymentEscrow.getAddress(), amount);

      await expect(
        paymentEscrow.connect(payer).createEscrow(
          payee.address,
          await mockToken.getAddress(),
          amount,
          3600
        )
      ).to.emit(paymentEscrow, "EscrowCreated").withArgs(0, payer.address, amount);
    });
  });

  describe("releaseEscrow", function () {
    it("should release escrow to payee", async function () {
      const amount = ethers.parseEther("100");
      await mockToken.connect(payer).approve(await paymentEscrow.getAddress(), amount);

      await paymentEscrow.connect(payer).createEscrow(
        payee.address,
        await mockToken.getAddress(),
        amount,
        3600
      );

      const payeeBalanceBefore = await mockToken.balanceOf(payee.address);
      await paymentEscrow.connect(payer).releaseEscrow(0);
      const payeeBalanceAfter = await mockToken.balanceOf(payee.address);

      expect(payeeBalanceAfter - payeeBalanceBefore).to.equal(amount);
    });

    it("should not allow double release", async function () {
      const amount = ethers.parseEther("100");
      await mockToken.connect(payer).approve(await paymentEscrow.getAddress(), amount);

      await paymentEscrow.connect(payer).createEscrow(
        payee.address,
        await mockToken.getAddress(),
        amount,
        3600
      );

      await paymentEscrow.connect(payer).releaseEscrow(0);
      await expect(
        paymentEscrow.connect(payer).releaseEscrow(0)
      ).to.be.revertedWith("Already settled");
    });

    it("should not allow unauthorized release", async function () {
      const amount = ethers.parseEther("100");
      await mockToken.connect(payer).approve(await paymentEscrow.getAddress(), amount);

      await paymentEscrow.connect(payer).createEscrow(
        payee.address,
        await mockToken.getAddress(),
        amount,
        3600
      );

      await expect(
        paymentEscrow.connect(payee).releaseEscrow(0)
      ).to.be.revertedWith("Not authorized");
    });
  });

  describe("refundEscrow", function () {
    it("should refund escrow to payer after lock expires", async function () {
      const amount = ethers.parseEther("100");
      await mockToken.connect(payer).approve(await paymentEscrow.getAddress(), amount);

      await paymentEscrow.connect(payer).createEscrow(
        payee.address,
        await mockToken.getAddress(),
        amount,
        1
      );

      await ethers.provider.send("evm_increaseTime", [2]);
      await ethers.provider.send("evm_mine");

      const payerBalanceBefore = await mockToken.balanceOf(payer.address);
      await paymentEscrow.connect(payer).refundEscrow(0);
      const payerBalanceAfter = await mockToken.balanceOf(payer.address);

      expect(payerBalanceAfter - payerBalanceBefore).to.equal(amount);
    });

    it("should not allow refund before lock expires", async function () {
      const amount = ethers.parseEther("100");
      await mockToken.connect(payer).approve(await paymentEscrow.getAddress(), amount);

      await paymentEscrow.connect(payer).createEscrow(
        payee.address,
        await mockToken.getAddress(),
        amount,
        3600
      );

      await expect(
        paymentEscrow.connect(payer).refundEscrow(0)
      ).to.be.revertedWith("Lock not expired");
    });

    it("should not allow non-payer to refund", async function () {
      const amount = ethers.parseEther("100");
      await mockToken.connect(payer).approve(await paymentEscrow.getAddress(), amount);

      await paymentEscrow.connect(payer).createEscrow(
        payee.address,
        await mockToken.getAddress(),
        amount,
        1
      );

      await ethers.provider.send("evm_increaseTime", [2]);
      await ethers.provider.send("evm_mine");

      await expect(
        paymentEscrow.connect(payee).refundEscrow(0)
      ).to.be.revertedWith("Not payer");
    });
  });
});
