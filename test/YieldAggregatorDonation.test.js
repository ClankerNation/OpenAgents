const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("YieldAggregator donation hardening", function () {
  const parse = ethers.parseEther;

  let owner;
  let depositor;
  let victim;
  let attacker;
  let strategy;
  let asset;
  let vault;

  async function deployVault() {
    [owner, depositor, victim, attacker, strategy] = await ethers.getSigners();

    const MockERC20 = await ethers.getContractFactory("MockERC20");
    asset = await MockERC20.deploy("Mock Asset", "MA");
    await asset.waitForDeployment();

    const YieldAggregator = await ethers.getContractFactory("YieldAggregator");
    vault = await YieldAggregator.deploy(await asset.getAddress());
    await vault.waitForDeployment();

    for (const user of [depositor, victim, attacker]) {
      await asset.mint(user.address, parse("1000"));
      await asset.connect(user).approve(await vault.getAddress(), parse("1000"));
    }
  }

  beforeEach(async function () {
    await deployVault();
  });

  it("reverts deposits that would mint fewer than minShares", async function () {
    await expect(vault.connect(depositor).deposit(parse("100"), parse("100.000000000000000001"))).to.be.revertedWith(
      "Vault: slippage"
    );
  });

  it("uses internal accounting so small donations do not dilute deposits or inflate withdrawals", async function () {
    await vault.connect(depositor).deposit(parse("100"), parse("100"));
    await asset.connect(attacker).transfer(await vault.getAddress(), parse("4"));

    await expect(vault.connect(victim).deposit(parse("100"), parse("100")))
      .to.emit(vault, "Deposit")
      .withArgs(victim.address, parse("100"), parse("100"));
    expect(await vault.shares(victim.address)).to.equal(parse("100"));
    expect(await vault.totalAssets()).to.equal(parse("200"));
    expect(await vault.actualManagedAssets()).to.equal(parse("204"));

    await expect(vault.connect(depositor).withdraw(parse("100")))
      .to.emit(vault, "Withdraw")
      .withArgs(depositor.address, parse("100"), parse("100"));
  });

  it("reverts when actual assets deviate from accounted assets by more than five percent", async function () {
    await vault.connect(depositor).deposit(parse("100"), parse("100"));
    await asset.connect(attacker).transfer(await vault.getAddress(), parse("6"));

    await expect(vault.connect(victim).deposit(parse("100"), parse("100"))).to.be.revertedWith(
      "Vault: price deviation"
    );
  });

  it("rejects zero-address strategies and only allocates internally accounted liquid assets", async function () {
    await expect(vault.addStrategy(ethers.ZeroAddress)).to.be.revertedWith("Vault: zero strategy");

    await vault.connect(depositor).deposit(parse("100"), parse("100"));
    await vault.addStrategy(strategy.address);
    await expect(vault.allocate(0, parse("101"))).to.be.revertedWith("Vault: insufficient balance");
    await expect(vault.allocate(0, parse("40"))).to.emit(vault, "StrategyAllocated").withArgs(0, parse("40"));
  });
});
