/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("YieldAggregator Donation Attack Fix", function () {
  let vault, token;
  let owner, user1, user2;

  before(async function () {
    [owner, user1, user2] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("AgentToken");
    token = await Token.deploy("Test Token", "TT", ethers.parseEther("1000000"));
    await token.waitForDeployment();

    const Vault = await ethers.getContractFactory("YieldAggregator");
    vault = await Vault.deploy(token.target);
    await vault.waitForDeployment();

    // Fund users
    await token.transfer(user1.address, ethers.parseEther("1000"));
    await token.transfer(user2.address, ethers.parseEther("1000"));
    await token.connect(user1).approve(vault.target, ethers.MaxUint256);
    await token.connect(user2).approve(vault.target, ethers.MaxUint256);
  });

  it("should enforce minShares on deposit", async function () {
    const amount = ethers.parseEther("100");
    // First deposit
    await vault.connect(user1).deposit(amount, amount);
    
    // Second deposit with unrealistic minShares should revert
    await expect(
      vault.connect(user2).deposit(amount, ethers.parseEther("200"))
    ).to.be.revertedWith("Vault: slippage exceeded");
  });

  it("should use internal accounting for withdrawal to prevent donation attacks", async function () {
    const depositAmount = ethers.parseEther("100");
    await vault.connect(user2).deposit(depositAmount, 0);
    
    // Donate tokens directly to vault (donation attack)
    await token.connect(user1).transfer(vault.target, ethers.parseEther("500"));
    
    // User2 withdraws their shares
    const shares = await vault.shares(user2.address);
    await vault.connect(user2).withdraw(shares);
    
    // User2 should only get back their original deposit (100), not 100 + share of donation
    const balance = await token.balanceOf(user2.address);
    // Initial was 1000, deposited 100, so should be 900 + 100 = 1000
    expect(balance).to.equal(ethers.parseEther("1000"));
  });

  it("should reject zero address strategy", async function () {
    await expect(
      vault.addStrategy(ethers.ZeroAddress)
    ).to.be.revertedWith("Vault: zero address strategy");
  });
});
