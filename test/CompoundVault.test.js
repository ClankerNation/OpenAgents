const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("CompoundVault strategy accounting", function () {
  async function deployVault() {
    const [owner, user, feeRecipient] = await ethers.getSigners();

    const MockERC20 = await ethers.getContractFactory("MockERC20");
    const baseToken = await MockERC20.deploy("Base", "BASE");
    await baseToken.waitForDeployment();
    const rewardToken = await MockERC20.deploy("Reward", "RWD");
    await rewardToken.waitForDeployment();

    const MockCompoundStrategy = await ethers.getContractFactory("MockCompoundStrategy");
    const strategy = await MockCompoundStrategy.deploy(await baseToken.getAddress());
    await strategy.waitForDeployment();

    const CompoundVault = await ethers.getContractFactory("CompoundVault");
    const vault = await CompoundVault.deploy(
      await baseToken.getAddress(),
      await rewardToken.getAddress(),
      await strategy.getAddress(),
      feeRecipient.address,
      0,
    );
    await vault.waitForDeployment();
    await strategy.setVault(await vault.getAddress());

    const depositAmount = ethers.parseEther("100");
    await baseToken.mint(user.address, depositAmount);
    await baseToken.connect(user).approve(await vault.getAddress(), depositAmount);
    await vault.connect(user).deposit(depositAmount);

    return { baseToken, strategy, user, vault };
  }

  it("increases share price when the strategy returns positive yield", async function () {
    const { strategy, vault } = await deployVault();
    const profit = ethers.parseEther("25");

    await strategy.setNextDelta(profit);

    await expect(vault.compound())
      .to.emit(vault, "Compounded")
      .withArgs(profit, ethers.parseEther("1.25"));

    expect(await vault.totalDeposited()).to.equal(ethers.parseEther("125"));
    expect(await vault.pricePerShare()).to.equal(ethers.parseEther("1.25"));
    expect(await vault.totalLoss()).to.equal(0n);
  });

  it("leaves accounting unchanged when the strategy returns zero yield", async function () {
    const { strategy, vault } = await deployVault();

    await strategy.setNextDelta(0);

    await expect(vault.compound())
      .to.emit(vault, "Compounded")
      .withArgs(0, ethers.parseEther("1"));

    expect(await vault.totalDeposited()).to.equal(ethers.parseEther("100"));
    expect(await vault.pricePerShare()).to.equal(ethers.parseEther("1"));
    expect(await vault.totalLoss()).to.equal(0n);
  });

  it("decreases share price and accumulates totalLoss when the strategy loses funds", async function () {
    const { strategy, vault } = await deployVault();
    const loss = ethers.parseEther("25");

    await strategy.setNextDelta(-loss);

    await expect(vault.compound())
      .to.emit(vault, "StrategyLoss")
      .withArgs(loss, ethers.parseEther("0.75"));

    expect(await vault.totalDeposited()).to.equal(ethers.parseEther("75"));
    expect(await vault.pricePerShare()).to.equal(ethers.parseEther("0.75"));
    expect(await vault.totalLoss()).to.equal(loss);
  });
});
