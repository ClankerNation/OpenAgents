const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PaymentEscrow — Issue #181: SafeERC20 Fix", function () {
  let escrow, token, owner, payer, payee;

  beforeEach(async function () {
    [owner, payer, payee] = await ethers.getSigners();

    // Deploy mock non-reverting ERC20 (returns false instead of reverting)
    const MockToken = await ethers.getContractFactory("contracts/mocks/MockNonRevertingERC20.sol:MockNonRevertingERC20");
    token = await MockToken.deploy("Mock", "MCK", ethers.parseEther("1000000"));
    await token.waitForDeployment();

    // Give payer some tokens
    await token.transfer(payer.address, ethers.parseEther("1000"));

    const Escrow = await ethers.getContractFactory("PaymentEscrow");
    escrow = await Escrow.deploy();
    await escrow.waitForDeployment();
  });

  it("createEscrow uses safeTransferFrom — reverts on non-standard token failure", async function () {
    // Approve escrow
    await token.connect(payer).approve(await escrow.getAddress(), ethers.parseEther("100"));

    // Create escrow should work
    const tx = await escrow.connect(payer).createEscrow(
      payee.address,
      await token.getAddress(),
      ethers.parseEther("100"),
      3600
    );
    const rc = await tx.wait();
    expect(rc.logs.find(l => l.fragment?.name === "EscrowCreated")).to.not.be.undefined;
  });

  it("releaseEscrow uses safeTransfer — reverts on failure", async function () {
    await token.connect(payer).approve(await escrow.getAddress(), ethers.parseEther("100"));
    const tx = await escrow.connect(payer).createEscrow(
      payee.address,
      await token.getAddress(),
      ethers.parseEther("100"),
      3600
    );
    const rc = await tx.wait();
    const escrowId = rc.logs.find(l => l.fragment?.name === "EscrowCreated").args.escrowId;

    // Release
    await expect(escrow.connect(payer).releaseEscrow(escrowId))
      .to.emit(escrow, "EscrowReleased");

    // Payee should have received tokens
    expect(await token.balanceOf(payee.address)).to.equal(ethers.parseEther("100"));
  });

  it("refundEscrow uses safeTransfer — reverts on failure", async function () {
    await token.connect(payer).approve(await escrow.getAddress(), ethers.parseEther("100"));
    const tx = await escrow.connect(payer).createEscrow(
      payee.address,
      await token.getAddress(),
      ethers.parseEther("100"),
      1 // 1 second lock
    );
    const rc = await tx.wait();
    const escrowId = rc.logs.find(l => l.fragment?.name === "EscrowCreated").args.escrowId;

    // Wait for lock to expire
    await ethers.provider.send("evm_increaseTime", [2]);
    await ethers.provider.send("evm_mine", []);

    // Refund
    await expect(escrow.connect(payer).refundEscrow(escrowId))
      .to.emit(escrow, "EscrowRefunded");
  });
});
