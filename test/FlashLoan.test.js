const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("FlashLoan", function () {
  let flashLoan, mockToken;
  let owner, borrower;

  beforeEach(async function () {
    [owner, borrower] = await ethers.getSigners();

    // Deploy mock ERC20 token
    const ERC20 = await ethers.getContractFactory("ERC20");
    mockToken = await ERC20.deploy("Test Token", "TST");
    await mockToken.deployed();

    // Mint tokens to owner for pool
    await mockToken.mint(owner.address, ethers.parseEther("10000"));
    await mockToken.mint(borrower.address, ethers.parseEther("1000"));

    // Deploy FlashLoan
    const FlashLoan = await ethers.getContractFactory("FlashLoan");
    flashLoan = await FlashLoan.deploy(mockToken.target);
    await flashLoan.deployed();

    // Owner deposits tokens into pool
    await mockToken
      .connect(owner)
      .approve(flashLoan.target, ethers.parseEther("5000"));
    await flashLoan.deposit(ethers.parseEther("5000"));
  });

  it("should reject fee less than 1", async function () {
    await expect(
      flashLoan.connect(borrower).issueLoan(100, 0, "0x")
    ).to.be.revertedWith("Fee must be at least 1");
  });

  it("should reject loan exceeding 50% of pool", async function () {
    const pool = await flashLoan.getPool();
    await expect(
      flashLoan.connect(borrower).issueLoan(pool + 1, 1, "0x")
    ).to.be.revertedWith("Loan exceeds 50% of pool");
  });

  it("should pause and unpause", async function () {
    await flashLoan.connect(owner).pause();
    expect(await flashLoan.isPaused()).to.be.true;

    await expect(
      flashLoan.connect(borrower).issueLoan(100, 1, "0x")
    ).to.be.revertedWith("Paused");

    await flashLoan.connect(owner).unpause();
    expect(await flashLoan.isPaused()).to.be.false;
  });

  it("should prevent rebasing attack (debt exceeds pool)", async function () {
    const pool = await flashLoan.getPool();
    // Try to issue debt that would exceed pool even if fee is small
    await expect(
      flashLoan.connect(borrower).issueLoan(pool / 2, 1, "0x")
    ).to.not.be.reverted;

    // Pool now has less available for second loan
    const poolAfter = await flashLoan.getPool();
    await expect(
      flashLoan.connect(borrower).issueLoan(poolAfter / 2 + 1, 1, "0x")
    ).to.be.revertedWith("Debt exceeds pool (rebasing safety)");
  });
});
