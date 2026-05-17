const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PaymentEscrow", function () {
  let paymentEscrow;
  let standardToken;
  let feeToken;
  let owner, payer, payee, other;

  before(async function () {
    [owner, payer, payee, other] = await ethers.getSigners();

    // Deploy standard ERC20 mock
    const MockERC20Factory = await ethers.getContractFactory("MockERC20");
    standardToken = await MockERC20Factory.deploy("Standard", "STD");
    await standardToken.waitForDeployment();

    // Deploy fee-on-transfer token
    const FeeTokenFactory = await ethers.getContractFactory("FeeOnTransferToken");
    feeToken = await FeeTokenFactory.deploy();
    await feeToken.waitForDeployment();

    // Deploy PaymentEscrow
    const PaymentEscrowFactory = await ethers.getContractFactory("PaymentEscrow");
    paymentEscrow = await PaymentEscrowFactory.deploy();
    await paymentEscrow.waitForDeployment();

    // Mint standard tokens to payer
    await standardToken.mint(payer.address, ethers.parseEther("10000"));
    await standardToken.mint(other.address, ethers.parseEther("10000"));

    // Mint fee tokens — FeeOnTransferToken already mints to deployer (owner)
    await feeToken.transfer(payer.address, ethers.parseEther("10000"));
    await feeToken.transfer(other.address, ethers.parseEther("10000"));
  });

  describe("createEscrow — standard ERC20", function () {
    it("should create an escrow with the correct amount", async function () {
      const amount = ethers.parseEther("100");
      await standardToken.connect(payer).approve(
        await paymentEscrow.getAddress(),
        amount
      );

      const tx = await paymentEscrow
        .connect(payer)
        .createEscrow(payee.address, await standardToken.getAddress(), amount, 86400);

      const receipt = await tx.wait();

      // Parse EscrowCreated event
      const event = receipt.logs.find(
        (log) => log.fragment && log.fragment.name === "EscrowCreated"
      );
      expect(event).to.not.be.undefined;
      expect(event.args.amount).to.equal(amount);

      const escrow = await paymentEscrow.escrows(0);
      expect(escrow.amount).to.equal(amount);
      expect(escrow.payer).to.equal(payer.address);
      expect(escrow.payee).to.equal(payee.address);
    });

    it("should reject zero amount", async function () {
      await expect(
        paymentEscrow
          .connect(payer)
          .createEscrow(
            payee.address,
            await standardToken.getAddress(),
            0,
            86400
          )
      ).to.be.revertedWith("Amount must be > 0");
    });

    it("should reject zero payee address", async function () {
      const amount = ethers.parseEther("100");
      await standardToken.connect(payer).approve(
        await paymentEscrow.getAddress(),
        amount
      );

      await expect(
        paymentEscrow
          .connect(payer)
          .createEscrow(
            ethers.ZeroAddress,
            await standardToken.getAddress(),
            amount,
            86400
          )
      ).to.be.revertedWith("Invalid payee");
    });

    it("should reject zero token address", async function () {
      const amount = ethers.parseEther("100");
      await expect(
        paymentEscrow
          .connect(payer)
          .createEscrow(
            payee.address,
            ethers.ZeroAddress,
            amount,
            86400
          )
      ).to.be.revertedWith("Invalid token");
    });
  });

  describe("createEscrow — fee-on-transfer token", function () {
    it("should store the actual received amount (not input amount)", async function () {
      const inputAmount = ethers.parseEther("100"); // 100 tokens
      const expectedFee = (inputAmount * 500n) / 10000n; // 5% fee = 5 tokens
      const expectedReceived = inputAmount - expectedFee; // 95 tokens

      await feeToken.connect(payer).approve(
        await paymentEscrow.getAddress(),
        inputAmount
      );

      const tx = await paymentEscrow
        .connect(payer)
        .createEscrow(
          payee.address,
          await feeToken.getAddress(),
          inputAmount,
          86400
        );

      const receipt = await tx.wait();
      const event = receipt.logs.find(
        (log) => log.fragment && log.fragment.name === "EscrowCreated"
      );

      // Event emits actual received amount, not input
      expect(event.args.amount).to.equal(expectedReceived);

      // Escrow storage records actual received amount
      const escrow = await paymentEscrow.escrows(1); // escrowId 1 (0 was standard token test)
      expect(escrow.amount).to.equal(expectedReceived);
      expect(escrow.amount).to.be.lt(inputAmount);
      expect(escrow.amount).to.be.gt(0);
    });

    it("should handle fee-on-transfer correctly for different amounts", async function () {
      const inputAmount = ethers.parseEther("1000"); // 1000 tokens
      const expectedFee = (inputAmount * 500n) / 10000n; // 50 tokens
      const expectedReceived = inputAmount - expectedFee; // 950 tokens

      await feeToken.connect(payer).approve(
        await paymentEscrow.getAddress(),
        inputAmount
      );

      await paymentEscrow
        .connect(payer)
        .createEscrow(
          payee.address,
          await feeToken.getAddress(),
          inputAmount,
          86400
        );

      const escrow = await paymentEscrow.escrows(2);
      expect(escrow.amount).to.equal(expectedReceived);
    });
  });

  describe("releaseEscrow", function () {
    it("should release funds to payee with standard token", async function () {
      const payeeBalanceBefore = await standardToken.balanceOf(payee.address);

      await paymentEscrow.connect(payer).releaseEscrow(0);

      const payeeBalanceAfter = await standardToken.balanceOf(payee.address);
      expect(payeeBalanceAfter - payeeBalanceBefore).to.equal(
        ethers.parseEther("100")
      );

      const escrow = await paymentEscrow.escrows(0);
      expect(escrow.released).to.be.true;
    });

    it("should release correct amount with fee-on-transfer token", async function () {
      // Escrow 1 has 95 tokens from fee-on-transfer (100 input - 5% fee)
      // On release, another 5% fee applies: 95 * 0.95 = 90.25
      const payeeBalanceBefore = await feeToken.balanceOf(payee.address);

      await paymentEscrow.connect(payer).releaseEscrow(1);

      const payeeBalanceAfter = await feeToken.balanceOf(payee.address);

      // 95 tokens stored, 5% fee on transfer out = 90.25 received
      expect(payeeBalanceAfter - payeeBalanceBefore).to.equal(
        ethers.parseEther("90.25")
      );

      const escrow = await paymentEscrow.escrows(1);
      expect(escrow.released).to.be.true;
    });

    it("should allow owner to release escrow", async function () {
      // Escrow 2 has 950 fee-tokens (1000 input - 5% fee)
      // On release, 5% fee: 950 * 0.95 = 902.5
      const payeeBalanceBefore = await feeToken.balanceOf(payee.address);

      await paymentEscrow.connect(owner).releaseEscrow(2);

      const payeeBalanceAfter = await feeToken.balanceOf(payee.address);
      expect(payeeBalanceAfter - payeeBalanceBefore).to.equal(
        ethers.parseEther("902.5")
      );
    });

    it("should not allow unauthorized release", async function () {
      const amount = ethers.parseEther("50");
      await standardToken.connect(other).approve(
        await paymentEscrow.getAddress(),
        amount
      );
      await paymentEscrow
        .connect(other)
        .createEscrow(payee.address, await standardToken.getAddress(), amount, 86400);

      await expect(
        paymentEscrow.connect(payer).releaseEscrow(3)
      ).to.be.revertedWith("Not authorized");
    });

    it("should not allow double release", async function () {
      await expect(
        paymentEscrow.connect(payer).releaseEscrow(0)
      ).to.be.revertedWith("Already settled");
    });
  });

  describe("refundEscrow", function () {
    it("should refund to payer after lock expires", async function () {
      const amount = ethers.parseEther("200");
      await standardToken.connect(payer).approve(
        await paymentEscrow.getAddress(),
        amount
      );
      await paymentEscrow
        .connect(payer)
        .createEscrow(payee.address, await standardToken.getAddress(), amount, 1); // 1 second lock

      const escrowId = await paymentEscrow.escrowCount() - 1n;

      // Advance time past lock
      await ethers.provider.send("evm_increaseTime", [2]);
      await ethers.provider.send("evm_mine");

      const payerBalanceBefore = await standardToken.balanceOf(payer.address);
      await paymentEscrow.connect(payer).refundEscrow(escrowId);
      const payerBalanceAfter = await standardToken.balanceOf(payer.address);

      expect(payerBalanceAfter - payerBalanceBefore).to.equal(amount);

      const escrow = await paymentEscrow.escrows(escrowId);
      expect(escrow.refunded).to.be.true;
    });

    it("should refund correct amount with fee-on-transfer token", async function () {
      const inputAmount = ethers.parseEther("50");
      // 5% fee on deposit: 47.5 stored. 5% fee on refund: 47.5 * 0.95 = 45.125

      await feeToken.connect(payer).approve(
        await paymentEscrow.getAddress(),
        inputAmount
      );
      await paymentEscrow
        .connect(payer)
        .createEscrow(payee.address, await feeToken.getAddress(), inputAmount, 1);

      const escrowId = await paymentEscrow.escrowCount() - 1n;

      await ethers.provider.send("evm_increaseTime", [2]);
      await ethers.provider.send("evm_mine");

      const payerBalanceBefore = await feeToken.balanceOf(payer.address);
      await paymentEscrow.connect(payer).refundEscrow(escrowId);
      const payerBalanceAfter = await feeToken.balanceOf(payer.address);

      expect(payerBalanceAfter - payerBalanceBefore).to.equal(
        ethers.parseEther("45.125")
      );
    });

    it("should not allow refund before lock expires", async function () {
      const amount = ethers.parseEther("50");
      await standardToken.connect(payer).approve(
        await paymentEscrow.getAddress(),
        amount
      );
      await paymentEscrow
        .connect(payer)
        .createEscrow(payee.address, await standardToken.getAddress(), amount, 3600);

      const escrowId = await paymentEscrow.escrowCount() - 1n;

      await expect(
        paymentEscrow.connect(payer).refundEscrow(escrowId)
      ).to.be.revertedWith("Lock not expired");
    });

    it("should not allow non-payer to refund", async function () {
      // Create a fresh escrow with a long lock
      const amount = ethers.parseEther("10");
      await standardToken.connect(payer).approve(
        await paymentEscrow.getAddress(),
        amount
      );
      await paymentEscrow
        .connect(payer)
        .createEscrow(payee.address, await standardToken.getAddress(), amount, 3600);
      const escrowId = await paymentEscrow.escrowCount() - 1n;

      // Advance past lock
      await ethers.provider.send("evm_increaseTime", [3601]);
      await ethers.provider.send("evm_mine");

      await expect(
        paymentEscrow.connect(other).refundEscrow(escrowId)
      ).to.be.revertedWith("Not payer");
    });
  });

  describe("escrowCount tracking", function () {
    it("should increment escrowCount correctly", async function () {
      const countBefore = await paymentEscrow.escrowCount();
      expect(countBefore).to.be.gt(0); // Already created several escrows
    });
  });
});
