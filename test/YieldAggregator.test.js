const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("YieldAggregator donation attack hardening (#21)", function () {
  let asset;
  let vault;
  let owner;
  let alice;
  let bob;
  let attacker;

  const ether = (n) => ethers.parseEther(String(n));

  beforeEach(async function () {
    [owner, alice, bob, attacker] = await ethers.getSigners();

    const MockERC20 = await ethers.getContractFactory("MockERC20");
    asset = await MockERC20.deploy("Mock USD", "mUSD");
    await asset.waitForDeployment();

    const YieldAggregator = await ethers.getContractFactory("YieldAggregator");
    vault = await YieldAggregator.deploy(await asset.getAddress());
    await vault.waitForDeployment();

    await asset.mint(alice.address, ether(10000));
    await asset.mint(bob.address, ether(10000));
    await asset.mint(attacker.address, ether(10000));
  });

  async function approveAndDeposit(user, amount, minShares) {
    const vaultAddress = await vault.getAddress();
    await asset.connect(user).approve(vaultAddress, amount);
    return vault.connect(user).deposit(amount, minShares);
  }

  it("reverts deposit when minted shares are below minShares", async function () {
    await approveAndDeposit(alice, ether(100), ether(100));
    await asset.connect(attacker).transfer(await vault.getAddress(), ether(500));
    const preview = await vault.previewDeposit(ether(10));
    await expect(approveAndDeposit(bob, ether(10), preview + 1n)).to.be.revertedWith(
      "Vault: insufficient shares minted",
    );
  });

  it("uses internal accounting on withdraw (donation cannot inflate payout)", async function () {
    await approveAndDeposit(alice, ether(100), ether(100));
    await approveAndDeposit(bob, ether(100), ether(100));
    const accounted = await vault.internalAssets();
    const donation = (accounted * 400n) / 10000n;
    await asset.connect(attacker).transfer(await vault.getAddress(), donation);

    const aliceShares = await vault.shares(alice.address);
    const before = await asset.balanceOf(alice.address);
    await vault.connect(alice).withdraw(aliceShares);
    const received = (await asset.balanceOf(alice.address)) - before;

    expect(received).to.equal(ether(100));
    expect(await vault.internalAssets()).to.equal(ether(100));
  });

  it("rejects zero-address strategy", async function () {
    await expect(vault.connect(owner).addStrategy(ethers.ZeroAddress)).to.be.revertedWith(
      "Vault: zero strategy address",
    );
  });

  it("reverts withdraw when vault balance exceeds internal assets by more than 5%", async function () {
    await approveAndDeposit(alice, ether(100), ether(100));
    const accounted = await vault.internalAssets();
    const excess = (accounted * 600n) / 10000n;
    await asset.connect(attacker).transfer(await vault.getAddress(), excess);
    const aliceShares = await vault.shares(alice.address);
    await expect(vault.connect(alice).withdraw(aliceShares)).to.be.revertedWith(
      "Vault: price deviation exceeds 5%",
    );
  });

  it("allows withdraw after owner reports strategy returns", async function () {
    await approveAndDeposit(alice, ether(100), ether(100));
    await asset.mint(owner.address, ether(10));
    await asset.connect(owner).approve(await vault.getAddress(), ether(10));
    await vault.connect(owner).reportReturns(ether(10));
    const shares = await vault.shares(alice.address);
    const before = await asset.balanceOf(alice.address);
    await vault.connect(alice).withdraw(shares);
    const received = (await asset.balanceOf(alice.address)) - before;
    expect(received).to.equal(ether(110));
  });
});

