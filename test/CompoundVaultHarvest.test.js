const { expect } = require("chai");
const { ethers } = require("hardhat");
const { anyValue } = require("@nomicfoundation/hardhat-chai-matchers/withArgs");

describe("CompoundVault harvest", function () {
  const parse = ethers.parseEther;

  let owner;
  let keeper;
  let stranger;
  let feeRecipient;
  let baseToken;
  let rewardToken;
  let vault;

  async function deployVault(feeBps = 1000) {
    [owner, keeper, stranger, feeRecipient] = await ethers.getSigners();

    const MockERC20 = await ethers.getContractFactory("MockERC20");
    baseToken = await MockERC20.deploy("Base Token", "BASE");
    await baseToken.waitForDeployment();

    rewardToken = await MockERC20.deploy("Reward Token", "RWD");
    await rewardToken.waitForDeployment();

    const CompoundVaultHarness = await ethers.getContractFactory("CompoundVaultHarness");
    vault = await CompoundVaultHarness.deploy(
      await baseToken.getAddress(),
      await rewardToken.getAddress(),
      ethers.ZeroAddress,
      feeRecipient.address,
      feeBps
    );
    await vault.waitForDeployment();
  }

  beforeEach(async function () {
    await deployVault();
  });

  it("restricts harvest to the owner or keeper", async function () {
    await rewardToken.mint(await vault.getAddress(), parse("10"));

    await expect(vault.connect(stranger).harvest()).to.be.revertedWith("Vault: not harvester");

    await vault.setKeeper(keeper.address);
    await expect(vault.connect(keeper).harvest()).to.emit(vault, "Harvested");
  });

  it("prices rewards with the current price per share instead of the cached value", async function () {
    await vault.setAccounting(parse("1"), parse("2"));
    await vault.setLastPricePerShare(parse("1"));
    await rewardToken.mint(await vault.getAddress(), parse("10"));

    await expect(vault.harvest())
      .to.emit(vault, "Harvested")
      .withArgs(parse("18"), parse("2"), anyValue);

    expect(await vault.lastPricePerShare()).to.equal(parse("2"));
    expect(await rewardToken.balanceOf(feeRecipient.address)).to.equal(parse("2"));
  });

  it("enforces a one-token minimum fee when fees are enabled", async function () {
    await deployVault(1);
    await rewardToken.mint(await vault.getAddress(), 1n);

    await expect(vault.harvest()).to.emit(vault, "Harvested").withArgs(0n, 1n, anyValue);
    expect(await rewardToken.balanceOf(feeRecipient.address)).to.equal(1n);
  });

  it("reverts when the estimated value is below the harvest threshold", async function () {
    await vault.setHarvestThreshold(2);
    await rewardToken.mint(await vault.getAddress(), 1);

    await expect(vault.harvest()).to.be.revertedWith("Vault: below threshold");
  });
});
