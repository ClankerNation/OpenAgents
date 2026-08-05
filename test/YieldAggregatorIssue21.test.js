const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("YieldAggregator security hardening", function () {
  async function deploy() {
    const [owner, donor, strategy] = await ethers.getSigners();
    const Token = await ethers.getContractFactory("YieldAggregatorTestToken");
    const token = await Token.deploy(10_000n);
    await token.waitForDeployment();
    const Vault = await ethers.getContractFactory("YieldAggregator");
    const vault = await Vault.deploy(await token.getAddress());
    await vault.waitForDeployment();
    return { owner, donor, strategy, token, vault };
  }

  it("enforces minShares and rejects a donation-induced price deviation", async function () {
    const { owner, donor, token, vault } = await deploy();
    await token.transfer(donor.address, 1_000n);
    await token.approve(await vault.getAddress(), 100n);
    await vault.deposit(100n, 100n);

    await token.connect(donor).transfer(await vault.getAddress(), 100n);
    await token.approve(await vault.getAddress(), 100n);
    await expect(vault.deposit(100n, 100n)).to.be.revertedWith("Vault: price deviation");
    expect(await vault.previewDeposit(100n)).to.equal(100n);
    expect(await vault.shares(owner.address)).to.equal(100n);
  });

  it("uses internal accounting for withdrawals instead of donated balance", async function () {
    const { owner, donor, token, vault } = await deploy();
    await token.transfer(donor.address, 1_000n);
    await token.approve(await vault.getAddress(), 100n);
    await vault.deposit(100n, 100n);
    await token.connect(donor).transfer(await vault.getAddress(), 100n);

    await vault.withdraw(100n);
    expect(await token.balanceOf(owner.address)).to.equal(9_000n);
    expect(await token.balanceOf(await vault.getAddress())).to.equal(100n);
    expect(await vault.totalDeposited()).to.equal(0n);
  });

  it("rejects zero strategies and preserves accounted assets across allocation", async function () {
    const { strategy, token, vault } = await deploy();
    await expect(vault.addStrategy(ethers.ZeroAddress)).to.be.revertedWith("Vault: zero strategy");
    await token.approve(await vault.getAddress(), 100n);
    await vault.deposit(100n, 100n);
    await vault.addStrategy(strategy.address);
    await vault.allocate(0n, 50n);

    expect(await vault.totalAssets()).to.equal(100n);
    await vault.withdraw(50n);
    expect(await token.balanceOf(await vault.getAddress())).to.equal(0n);
  });
});
