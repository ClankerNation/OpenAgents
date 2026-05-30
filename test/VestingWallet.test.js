const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("VestingWallet Migration", function () {
  let oldToken, newToken;
  let vestingWallet;
  let owner, beneficiary, user;

  const startOffset = 3600; // starts in 1 hour
  const cliffDuration = 3600; // 1 hour cliff
  const vestingDuration = 7200; // 2 hour duration (vests over 1 hour after cliff)
  const totalAllocation = ethers.parseEther("1000");

  beforeEach(async function () {
    [owner, beneficiary, user] = await ethers.getSigners();

    // Deploy mock tokens
    const StakingToken = await ethers.getContractFactory("StakingToken");
    oldToken = await StakingToken.deploy();
    await oldToken.waitForDeployment();

    newToken = await StakingToken.deploy();
    await newToken.waitForDeployment();

    // Deploy VestingWallet
    const VestingWallet = await ethers.getContractFactory("VestingWallet");
    const latestBlock = await ethers.provider.getBlock("latest");
    const startTime = latestBlock.timestamp + startOffset;

    vestingWallet = await VestingWallet.deploy(
      beneficiary.address,
      oldToken.target,
      startTime,
      cliffDuration,
      vestingDuration,
      totalAllocation,
      true // revocable
    );
    await vestingWallet.waitForDeployment();

    // Transfer old tokens to the contract
    await oldToken.mint(vestingWallet.target, totalAllocation);
  });

  it("should allow owner to migrate to a new token address if balance is sufficient", async function () {
    // Mint new token to VestingWallet to match the expected remaining amount
    await newToken.mint(vestingWallet.target, totalAllocation);

    // Perform migration
    const tx = await vestingWallet.connect(owner).migrateToken(newToken.target);

    // Verify event emission
    await expect(tx)
      .to.emit(vestingWallet, "TokenMigrated")
      .withArgs(oldToken.target, newToken.target);

    // Verify token reference updated
    const currentToken = await vestingWallet.token();
    expect(currentToken).to.equal(newToken.target);
  });

  it("should prevent non-owner from calling migrateToken", async function () {
    await newToken.mint(vestingWallet.target, totalAllocation);
    await expect(
      vestingWallet.connect(user).migrateToken(newToken.target)
    ).to.be.revertedWith("Vesting: not owner");
  });

  it("should prevent migration if new token balance is insufficient", async function () {
    // Only mint half the allocation
    await newToken.mint(vestingWallet.target, totalAllocation / 2n);

    await expect(
      vestingWallet.connect(owner).migrateToken(newToken.target)
    ).to.be.revertedWith("Vesting: insufficient new token balance");
  });

  it("should distribute claims using the new token after migration", async function () {
    // Mint new token to VestingWallet to match the expected remaining amount
    await newToken.mint(vestingWallet.target, totalAllocation);

    // Migrate
    await vestingWallet.connect(owner).migrateToken(newToken.target);

    // Advance time beyond cliff and vesting duration to vest fully
    const latestBlock = await ethers.provider.getBlock("latest");
    const start = await vestingWallet.start();
    const duration = await vestingWallet.vestingDuration();
    
    // Set timestamp to after vesting completes
    await ethers.provider.send("evm_setNextBlockTimestamp", [Number(start) + Number(duration) + 100]);
    await ethers.provider.send("evm_mine");

    // Beneficiary claims rewards
    const initialBeneficiaryBalance = await newToken.balanceOf(beneficiary.address);
    await vestingWallet.connect(beneficiary).release();

    // Verify beneficiary received the new token
    const finalBeneficiaryBalance = await newToken.balanceOf(beneficiary.address);
    expect(finalBeneficiaryBalance - initialBeneficiaryBalance).to.equal(totalAllocation);
  });
});
