const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("VestingWallet", function () {
  let vestingWallet, tokenV1, tokenV2;
  let owner, beneficiary, other;
  
  const TOTAL_ALLOCATION = ethers.utils.parseEther("1000");
  const CLIFF_DURATION = 30 * 24 * 60 * 60; // 30 days
  const VESTING_DURATION = 365 * 24 * 60 * 60; // 1 year

  beforeEach(async function () {
    [owner, beneficiary, other] = await ethers.getSigners();

    // Deploy mock ERC20 tokens
    const MockToken = await ethers.getContractFactory("MockERC20");
    tokenV1 = await MockToken.deploy("Token V1", "TKN1");
    await tokenV1.deployed();
    
    tokenV2 = await MockToken.deploy("Token V2", "TKN2");
    await tokenV2.deployed();

    // Get current block timestamp
    const startTime = await time.latest();

    // Deploy VestingWallet
    const VestingWallet = await ethers.getContractFactory("VestingWallet");
    vestingWallet = await VestingWallet.deploy(
      beneficiary.address,
      tokenV1.address,
      startTime,
      CLIFF_DURATION,
      VESTING_DURATION,
      TOTAL_ALLOCATION,
      true // revocable
    );
    await vestingWallet.deployed();

    // Fund the vesting wallet with V1 tokens
    await tokenV1.mint(vestingWallet.address, TOTAL_ALLOCATION);
  });

  describe("Token Migration", function () {
    it("should allow owner to migrate to new token", async function () {
      // Fund wallet with V2 tokens
      await tokenV2.mint(vestingWallet.address, TOTAL_ALLOCATION);

      // Migrate
      await expect(vestingWallet.migrateToken(tokenV2.address))
        .to.emit(vestingWallet, "TokenMigrated")
        .withArgs(tokenV1.address, tokenV2.address, TOTAL_ALLOCATION);

      // Verify token reference updated
      expect(await vestingWallet.token()).to.equal(tokenV2.address);
    });

    it("should reject migration with insufficient new token balance", async function () {
      // Fund wallet with only half the required V2 tokens
      const insufficientAmount = TOTAL_ALLOCATION.div(2);
      await tokenV2.mint(vestingWallet.address, insufficientAmount);

      await expect(vestingWallet.migrateToken(tokenV2.address))
        .to.be.revertedWith("Vesting: insufficient new token balance");
    });

    it("should reject migration from non-owner", async function () {
      await tokenV2.mint(vestingWallet.address, TOTAL_ALLOCATION);

      await expect(vestingWallet.connect(other).migrateToken(tokenV2.address))
        .to.be.revertedWith("Vesting: not owner");
    });

    it("should reject migration to zero address", async function () {
      await expect(vestingWallet.migrateToken(ethers.constants.AddressZero))
        .to.be.revertedWith("Vesting: zero address");
    });

    it("should reject migration to same token", async function () {
      await expect(vestingWallet.migrateToken(tokenV1.address))
        .to.be.revertedWith("Vesting: same token");
    });

    it("should reject migration after revocation", async function () {
      // Revoke first
      await vestingWallet.revoke();

      await tokenV2.mint(vestingWallet.address, TOTAL_ALLOCATION);

      await expect(vestingWallet.migrateToken(tokenV2.address))
        .to.be.revertedWith("Vesting: already revoked");
    });

    it("should allow claims after migration", async function () {
      // Move past cliff
      await time.increase(CLIFF_DURATION + 1);

      // Release some tokens before migration
      await vestingWallet.connect(beneficiary).release();
      const releasedBefore = await vestingWallet.released();
      expect(releasedBefore).to.be.gt(0);

      // Calculate remaining obligation
      const remainingVesting = TOTAL_ALLOCATION.sub(releasedBefore);

      // Fund wallet with V2 tokens for remaining vesting
      await tokenV2.mint(vestingWallet.address, remainingVesting);

      // Migrate
      await vestingWallet.migrateToken(tokenV2.address);

      // Move forward in time
      await time.increase(30 * 24 * 60 * 60); // 30 more days

      // Get beneficiary's V2 balance before claim
      const balanceBefore = await tokenV2.balanceOf(beneficiary.address);

      // Claim with new token
      await vestingWallet.connect(beneficiary).release();

      // Verify V2 tokens were transferred
      const balanceAfter = await tokenV2.balanceOf(beneficiary.address);
      expect(balanceAfter).to.be.gt(balanceBefore);
    });

    it("should account for already released tokens in balance requirement", async function () {
      // Move past cliff and release some tokens
      await time.increase(CLIFF_DURATION + 30 * 24 * 60 * 60);
      await vestingWallet.connect(beneficiary).release();
      
      const released = await vestingWallet.released();
      const remaining = TOTAL_ALLOCATION.sub(released);

      // Fund with exactly the remaining amount (not full allocation)
      await tokenV2.mint(vestingWallet.address, remaining);

      // Migration should succeed with just the remaining amount
      await expect(vestingWallet.migrateToken(tokenV2.address))
        .to.emit(vestingWallet, "TokenMigrated")
        .withArgs(tokenV1.address, tokenV2.address, remaining);
    });
  });
});