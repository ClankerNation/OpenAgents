const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("CompoundVault", function () {
  const ONE_HUNDRED = ethers.parseEther("100");

  let owner, depositor, feeRecipient;
  let baseToken, rewardToken, strategy, vault;

  beforeEach(async function () {
    [owner, depositor, feeRecipient] = await ethers.getSigners();

    const MockVaultToken = await ethers.getContractFactory("MockVaultToken");
    baseToken = await MockVaultToken.deploy("Base Token", "BASE");
    rewardToken = await MockVaultToken.deploy("Reward Token", "RWD");

    const MockCompoundStrategy = await ethers.getContractFactory("MockCompoundStrategy");
    strategy = await MockCompoundStrategy.deploy(await baseToken.getAddress());

    const CompoundVault = await ethers.getContractFactory("CompoundVault");
    vault = await CompoundVault.deploy(
      await baseToken.getAddress(),
      await rewardToken.getAddress(),
      await strategy.getAddress(),
      feeRecipient.address,
      1_000
    );

    await baseToken.mint(depositor.address, ONE_HUNDRED);
    await baseToken.connect(depositor).approve(await vault.getAddress(), ONE_HUNDRED);
    await vault.connect(depositor).deposit(ONE_HUNDRED);
  });

  it("increases share price when the strategy returns positive yield", async function () {
    const yieldAmount = ethers.parseEther("10");

    await strategy.setNextReturn(yieldAmount);

    await expect(vault.connect(owner).compound())
      .to.emit(vault, "Compounded")
      .withArgs(yieldAmount, ethers.parseEther("1.1"));

    expect(await vault.totalDeposited()).to.equal(ethers.parseEther("110"));
    expect(await vault.totalLoss()).to.equal(0n);
    expect(await vault.pricePerShare()).to.equal(ethers.parseEther("1.1"));
    expect(await vault.lastPricePerShare()).to.equal(ethers.parseEther("1.1"));
  });

  it("keeps share price unchanged when the strategy returns zero yield", async function () {
    await expect(vault.connect(owner).compound())
      .to.emit(vault, "Compounded")
      .withArgs(0, ethers.parseEther("1"));

    expect(await vault.totalDeposited()).to.equal(ONE_HUNDRED);
    expect(await vault.totalLoss()).to.equal(0n);
    expect(await vault.pricePerShare()).to.equal(ethers.parseEther("1"));
    expect(await vault.lastPricePerShare()).to.equal(ethers.parseEther("1"));
  });

  it("decreases share price proportionally and accumulates totalLoss on strategy losses", async function () {
    await strategy.setNextReturn(-ethers.parseEther("15"));

    await expect(vault.connect(owner).compound())
      .to.emit(vault, "StrategyLoss")
      .withArgs(ethers.parseEther("15"));

    expect(await vault.totalDeposited()).to.equal(ethers.parseEther("85"));
    expect(await vault.totalLoss()).to.equal(ethers.parseEther("15"));
    expect(await vault.pricePerShare()).to.equal(ethers.parseEther("0.85"));
    expect(await vault.lastPricePerShare()).to.equal(ethers.parseEther("0.85"));

    await strategy.setNextReturn(-ethers.parseEther("5"));

    await expect(vault.connect(owner).compound())
      .to.emit(vault, "StrategyLoss")
      .withArgs(ethers.parseEther("5"));

    expect(await vault.totalDeposited()).to.equal(ethers.parseEther("80"));
    expect(await vault.totalLoss()).to.equal(ethers.parseEther("20"));
    expect(await vault.pricePerShare()).to.equal(ethers.parseEther("0.8"));
    expect(await vault.lastPricePerShare()).to.equal(ethers.parseEther("0.8"));
  });
});
