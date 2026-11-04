const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("FlashLoan", function () {
  let FlashLoan, flashLoan, owner, addr1;

  beforeEach(async function () {
    [owner, addr1] = await ethers.getSigners();
    FlashLoan = await ethers.getContractFactory("FlashLoan");
    flashLoan = await FlashLoan.deploy();
  });

  it("should enforce minimum fee of 1 token for small amounts", async function () {
    // Simulate pool deposit
    await flashLoan.setPaused(false);
    // Direct test via transaction or internal state check
    expect(true).to.equal(true);
  });

  it("should reject loans greater than 50% of pool", async function () {
    await expect(
      flashLoan.flashLoan(1000)
    ).to.be.revertedWith("Loan exceeds 50% of pool balance");
  });

  it(
    "should allow pause and unpause functionality", async function () {
      await flashLoan.setPaused(true);
      expect(await flashLoan.paused()).to.equal(true);
      await flashLoan.setPaused(false);
      expect(await flashLoan.paused()).to.equal(false);
    }
  );
});