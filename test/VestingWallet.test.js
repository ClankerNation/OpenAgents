const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("VestingWallet", function () {
  let vestingWallet, token1, token2;
  let owner, beneficiary, other;

  const TOTAL_ALLOCATION = ethers.utils.parseEther("1000");
  const CLIFF_DURATION = 30 * 24 * 3600; // 30 days
  const VESTING_DURATION = 365 * 24 * 3600; // 365 days
  const START_TIME = 1747400000;

  beforeEach(async function () {
    [owner, beneficiary, other] = await ethers.getSigners();

    // Deploy two mock ERC20 tokens for migration testing
    const MockToken = await ethers.getContractFactory("MockERC20");
    token1 = await MockToken.deploy("Token V1", "TKN1");
    await token1.deployed();
    token2 = await MockToken.deploy("Token V2", "TKN2");
    await token2.deployed();

    // Deploy VestingWallet
    const VestingWallet = await ethers.getContractFactory("VestingWallet");
    vestingWallet = await VestingWallet.deploy(
      beneficiary.address,
      token1.address,
      START_TIME,
      CLIFF_DURATION,
      VESTING_DURATION,
      TOTAL_ALLOCATION,
      true // revocable
    );
    await vestingWallet.deployed();

    // Fund the contract with old tokens
    await token1.mint(vestingWallet.address, TOTAL_ALLOCATION);
  });

  describe("migrateToken", function () {
    it("should allow owner to migrate to a new token", async function () {
      // Fund contract with new tokens
      await token2.mint(vestingWallet.address, TOTAL_ALLOCATION);

      // Migrate
      await expect(
        vestingWallet.connect(owner).migrateToken(token2.address)
      ).to.emit(vestingWallet, "TokenMigrated");

      // Verify token reference updated
      expect(await vestingWallet.token()).to.equal(token2.address);
    });

    it("should revert if caller is not owner", async function () {
      await token2.mint(vestingWallet.address, TOTAL_ALLOCATION);

      await expect(
        vestingWallet.connect(beneficiary).migrateToken(token2.address)
      ).to.be.revertedWith("Vesting: not owner");
    });

    it("should revert if new token is zero address", async function () {
      await expect(
        vestingWallet.connect(owner).migrateToken(ethers.constants.AddressZero)
      ).to.be.revertedWith("Vesting: zero address token");
    });

    it("should revert if new token is same as current", async function () {
      await expect(
        vestingWallet.connect(owner).migrateToken(token1.address)
      ).to.be.revertedWith("Vesting: same token");
    });

    it("should revert if new token has insufficient balance", async function () {
      // Only mint half the required amount
      await token2.mint(vestingWallet.address, TOTAL_ALLOCATION.div(2));

      await expect(
        vestingWallet.connect(owner).migrateToken(token2.address)
      ).to.be.revertedWith("Vesting: insufficient new token balance");
    });

    it("should revert if vesting has been revoked", async function () {
      await token2.mint(vestingWallet.address, TOTAL_ALLOCATION);

      // Revoke first
      await vestingWallet.connect(owner).revoke();

      await expect(
        vestingWallet.connect(owner).migrateToken(token2.address)
      ).to.be.revertedWith("Vesting: revoked");
    });

    it("should transfer old tokens back to owner on migration", async function () {
      await token2.mint(vestingWallet.address, TOTAL_ALLOCATION);

      const ownerBalanceBefore = await token1.balanceOf(owner.address);

      await vestingWallet.connect(owner).migrateToken(token2.address);

      const ownerBalanceAfter = await token1.balanceOf(owner.address);
      expect(ownerBalanceAfter.sub(ownerBalanceBefore)).to.equal(TOTAL_ALLOCATION);
    });

    it("should allow beneficiary to claim with new token after migration", async function () {
      await token2.mint(vestingWallet.address, TOTAL_ALLOCATION);

      // Migrate
      await vestingWallet.connect(owner).migrateToken(token2.address);

      // Move time past cliff + some vesting
      const vestedTime = START_TIME + CLIFF_DURATION + 180 * 24 * 3600; // half way
      await ethers.provider.send("evm_setNextBlockTimestamp", [vestedTime]);
      await ethers.provider.send("evm_mine");

      // Release should now use new token
      const releasable = await vestingWallet.releasable();
      expect(releasable).to.be.gt(0);

      const beneficiaryBalanceBefore = await token2.balanceOf(beneficiary.address);
      await vestingWallet.connect(beneficiary).release();
      const beneficiaryBalanceAfter = await token2.balanceOf(beneficiary.address);

      expect(beneficiaryBalanceAfter.sub(beneficiaryBalanceBefore)).to.equal(releasable);
    });

    it("should emit TokenMigrated event with correct parameters", async function () {
      await token2.mint(vestingWallet.address, TOTAL_ALLOCATION);

      const remaining = TOTAL_ALLOCATION; // nothing released yet

      await expect(
        vestingWallet.connect(owner).migrateToken(token2.address)
      ).to.emit(vestingWallet, "TokenMigrated")
        .withArgs(token1.address, token2.address, remaining);
    });
  });
});
