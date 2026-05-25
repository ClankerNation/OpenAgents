const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("CompoundVault strategy returns", function () {
  let owner;
  let depositor;
  let feeRecipient;
  let baseToken;
  let rewardToken;
  let vault;
  let strategy;

  const initialDeposit = ethers.parseEther("100");

  beforeEach(async function () {
    [owner, depositor, feeRecipient] = await ethers.getSigners();

    const MockVaultToken = await ethers.getContractFactory("MockVaultToken");
    baseToken = await MockVaultToken.deploy("Base Token", "BASE");
    await baseToken.waitForDeployment();

    rewardToken = await MockVaultToken.deploy("Reward Token", "RWD");
    await rewardToken.waitForDeployment();

    const MockCompoundStrategy = await ethers.getContractFactory("MockCompoundStrategy");
    strategy = await MockCompoundStrategy.deploy(await baseToken.getAddress());
    await strategy.waitForDeployment();

    const CompoundVault = await ethers.getContractFactory("CompoundVault");
    vault = await CompoundVault.deploy(
      await baseToken.getAddress(),
      await rewardToken.getAddress(),
      await strategy.getAddress(),
      feeRecipient.address,
      1000
    );
    await vault.waitForDeployment();
    await strategy.setVault(await vault.getAddress());

    await baseToken.mint(depositor.address, initialDeposit);
    await baseToken.connect(depositor).approve(await vault.getAddress(), initialDeposit);
    await vault.connect(depositor).deposit(initialDeposit);
  });

  it("increases share price when the strategy returns positive yield", async function () {
    const gain = ethers.parseEther("20");
    await strategy.setReturn(1, gain);

    await expect(vault.compound())
      .to.emit(vault, "Compounded")
      .withArgs(gain, ethers.parseEther("1.2"));

    expect(await vault.totalDeposited()).to.equal(ethers.parseEther("120"));
    expect(await vault.totalLoss()).to.equal(0n);
    expect(await vault.pricePerShare()).to.equal(ethers.parseEther("1.2"));
    expect(await vault.lastPricePerShare()).to.equal(ethers.parseEther("1.2"));
  });

  it("keeps accounting unchanged when the strategy returns zero yield", async function () {
    await strategy.setReturn(0, 0);

    await expect(vault.compound())
      .to.emit(vault, "Compounded")
      .withArgs(0, ethers.parseEther("1"));

    expect(await vault.totalDeposited()).to.equal(initialDeposit);
    expect(await vault.totalLoss()).to.equal(0n);
    expect(await vault.pricePerShare()).to.equal(ethers.parseEther("1"));
  });

  it("reduces share price, accumulates totalLoss, and emits StrategyLoss on losses", async function () {
    const loss = ethers.parseEther("25");
    await strategy.setReturn(2, loss);

    await expect(vault.compound())
      .to.emit(vault, "StrategyLoss")
      .withArgs(loss, ethers.parseEther("0.75"));

    expect(await vault.totalDeposited()).to.equal(ethers.parseEther("75"));
    expect(await vault.totalLoss()).to.equal(loss);
    expect(await vault.pricePerShare()).to.equal(ethers.parseEther("0.75"));
    expect(await vault.lastPricePerShare()).to.equal(ethers.parseEther("0.75"));
  });
});
