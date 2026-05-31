const { expect } = require("chai");
const { ethers } = require("hardhat");

/**
 * @contributor Codex
 * @platform-config Omitted by safety policy: full pre-session orchestration instructions are not embedded in source files.
 * @env os=Windows, arch=x64, home_dir=C:\Users\55093, working_dir=F:\jiedan\OpenAgents, shell=powershell
 * @timestamp 2026-05-30T20:44:08-07:00
 */
describe("CompoundVault compound validation", function () {
  async function deployFixture() {
    const [owner, user] = await ethers.getSigners();

    const AgentToken = await ethers.getContractFactory("AgentToken");
    const baseToken = await AgentToken.deploy("Base Token", "BASE", 0);
    await baseToken.waitForDeployment();

    const MockCompoundStrategy = await ethers.getContractFactory("MockCompoundStrategy");
    const mockStrategy = await MockCompoundStrategy.deploy(await baseToken.getAddress());
    await mockStrategy.waitForDeployment();

    const CompoundVault = await ethers.getContractFactory("CompoundVault");
    const vault = await CompoundVault.deploy(
      await baseToken.getAddress(),
      await baseToken.getAddress(),
      await mockStrategy.getAddress(),
      owner.address,
      1000
    );
    await vault.waitForDeployment();

    await mockStrategy.setVault(await vault.getAddress());

    const depositAmount = ethers.parseEther("100");
    await baseToken.mint(user.address, depositAmount);
    await baseToken.connect(user).approve(await vault.getAddress(), depositAmount);
    await vault.connect(user).deposit(depositAmount);

    return { owner, baseToken, mockStrategy, vault, depositAmount };
  }

  it("positive yield increases share price", async function () {
    const { vault, mockStrategy, depositAmount } = await deployFixture();
    const gain = ethers.parseEther("20");

    await mockStrategy.setNextDelta(gain);
    await expect(vault.compound())
      .to.emit(vault, "Compounded")
      .withArgs(gain, ethers.parseEther("1.2"));

    expect(await vault.totalDeposited()).to.equal(depositAmount + gain);
    expect(await vault.totalLoss()).to.equal(0n);
    expect(await vault.lastPricePerShare()).to.equal(ethers.parseEther("1.2"));
  });

  it("zero yield keeps share price unchanged", async function () {
    const { vault, mockStrategy, depositAmount } = await deployFixture();

    await mockStrategy.setNextDelta(0);
    await expect(vault.compound())
      .to.emit(vault, "Compounded")
      .withArgs(0, ethers.parseEther("1"));

    expect(await vault.totalDeposited()).to.equal(depositAmount);
    expect(await vault.totalLoss()).to.equal(0n);
    expect(await vault.lastPricePerShare()).to.equal(ethers.parseEther("1"));
  });

  it("negative yield decreases share price and tracks totalLoss", async function () {
    const { vault, mockStrategy } = await deployFixture();
    const loss = ethers.parseEther("25");

    await mockStrategy.setNextDelta(-loss);
    await expect(vault.compound())
      .to.emit(vault, "StrategyLoss")
      .withArgs(loss);

    expect(await vault.totalDeposited()).to.equal(ethers.parseEther("75"));
    expect(await vault.totalLoss()).to.equal(loss);
    expect(await vault.lastPricePerShare()).to.equal(ethers.parseEther("0.75"));
  });
});
