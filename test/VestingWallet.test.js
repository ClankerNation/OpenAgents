const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("VestingWallet Token Migration", function () {
  let vestingWallet, oldToken, newToken;
  let owner, beneficiary, attacker;
  let start, cliffDuration, vestingDuration, totalAllocation;

  beforeEach(async function () {
    [owner, beneficiary, attacker] = await ethers.getSigners();

    // Deploy tokens
    const AgentToken = await ethers.getContractFactory("AgentToken");
    oldToken = await AgentToken.deploy("Old OpenAgents Token", "OAT", ethers.parseEther("10000"));
    await oldToken.waitForDeployment();

    newToken = await AgentToken.deploy("New OpenAgents Token", "NAT", ethers.parseEther("10000"));
    await newToken.waitForDeployment();

    // Vesting configuration
    const latestBlock = await ethers.provider.getBlock("latest");
    start = latestBlock.timestamp + 100;
    cliffDuration = 1000;
    vestingDuration = 5000;
    totalAllocation = ethers.parseEther("1000");

    // Deploy VestingWallet
    const VestingWallet = await ethers.getContractFactory("VestingWallet");
    vestingWallet = await VestingWallet.deploy(
      beneficiary.address,
      oldToken.target,
      start,
      cliffDuration,
      vestingDuration,
      totalAllocation,
      true // revocable
    );
    await vestingWallet.waitForDeployment();

    // Fund VestingWallet with old tokens
    await oldToken.transfer(vestingWallet.target, totalAllocation);
  });

  it("should deploy with the correct initial parameters", async function () {
    expect(await vestingWallet.beneficiary()).to.equal(beneficiary.address);
    expect(await vestingWallet.token()).to.equal(oldToken.target);
    expect(await vestingWallet.totalAllocation()).to.equal(totalAllocation);
  });

  it("should fail to migrate if not called by the owner", async function () {
    await expect(
      vestingWallet.connect(attacker).migrateToken(newToken.target)
    ).to.be.revertedWith("Vesting: not owner");
  });

  it("should fail to migrate if invalid token address", async function () {
    await expect(
      vestingWallet.connect(owner).migrateToken(ethers.ZeroAddress)
    ).to.be.revertedWith("Vesting: invalid token");
  });

  it("should fail to migrate if new token balance is insufficient", async function () {
    // VestingWallet currently has 0 NAT tokens, but needs totalAllocation - released = 1000 NAT
    await expect(
      vestingWallet.connect(owner).migrateToken(newToken.target)
    ).to.be.revertedWith("Vesting: insufficient new token balance");
  });

  it("should migrate successfully when requirements are met", async function () {
    // Fund VestingWallet with enough NAT tokens (at least totalAllocation - released)
    await newToken.transfer(vestingWallet.target, totalAllocation);

    // Perform migration
    const tx = await vestingWallet.connect(owner).migrateToken(newToken.target);
    const receipt = await tx.wait();

    // In ethers v6, events are logs. Parse logs:
    const parsedLogs = receipt.logs.map(log => {
      try {
        return vestingWallet.interface.parseLog(log);
      } catch (e) {
        return null;
      }
    }).filter(Boolean);

    const event = parsedLogs.find(log => log.name === "TokenMigrated");
    expect(event).to.not.be.undefined;
    expect(event.args.oldToken).to.equal(oldToken.target);
    expect(event.args.newToken).to.equal(newToken.target);

    // Verify token address updated
    expect(await vestingWallet.token()).to.equal(newToken.target);
  });

  it("should allow claims of the new token after migration", async function () {
    // Fund with NAT tokens
    await newToken.transfer(vestingWallet.target, totalAllocation);

    // Migrate to NAT
    await vestingWallet.connect(owner).migrateToken(newToken.target);

    // Move time forward past cliff and partial vesting duration
    const elapsed = cliffDuration + 1000;
    await ethers.provider.send("evm_setNextBlockTimestamp", [start + elapsed]);
    await ethers.provider.send("evm_mine");

    // Releasable amount should be non-zero
    const releasable = await vestingWallet.releasable();
    expect(releasable).to.be.gt(0);

    // Release to beneficiary
    const beneficiaryInitialBalance = await newToken.balanceOf(beneficiary.address);
    await vestingWallet.connect(beneficiary).release();

    // Beneficiary should have received new tokens
    const beneficiaryFinalBalance = await newToken.balanceOf(beneficiary.address);
    expect(beneficiaryFinalBalance - beneficiaryInitialBalance).to.equal(await vestingWallet.released());
  });
});
