const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("VestingWallet safety hardening", function () {
  const MAX_UINT256 = (1n << 256n) - 1n;

  async function deployToken(initialSupply = 1_000_000n) {
    const AgentToken = await ethers.getContractFactory("AgentToken");
    const token = await AgentToken.deploy("Test Token", "TST", initialSupply);
    await token.waitForDeployment();
    return token;
  }

  async function deployWallet({ beneficiary, token, start, cliff, duration, allocation, revocable = true }) {
    const VestingWallet = await ethers.getContractFactory("VestingWallet");
    const wallet = await VestingWallet.deploy(
      beneficiary,
      await token.getAddress(),
      start,
      cliff,
      duration,
      allocation,
      revocable
    );
    await wallet.waitForDeployment();
    return wallet;
  }

  it("rejects zero-address beneficiaries and tokens", async function () {
    const [, beneficiary] = await ethers.getSigners();
    const token = await deployToken(1n);
    const VestingWallet = await ethers.getContractFactory("VestingWallet");
    const latest = await ethers.provider.getBlock("latest");
    const start = BigInt(latest.timestamp) + 1n;

    await expect(
      VestingWallet.deploy(
        ethers.ZeroAddress,
        await token.getAddress(),
        start,
        10n,
        20n,
        1n,
        true
      )
    ).to.be.revertedWith("Vesting: zero beneficiary");
    await expect(
      VestingWallet.deploy(beneficiary.address, ethers.ZeroAddress, start, 10n, 20n, 1n, true)
    ).to.be.revertedWith("Vesting: zero token");
  });

  it("calculates large allocations without multiplication overflow", async function () {
    const [, beneficiary] = await ethers.getSigners();
    const token = await deployToken(1n);
    const duration = 1n << 128n;
    const wallet = await deployWallet({
      beneficiary: beneficiary.address,
      token,
      start: 0n,
      cliff: 0n,
      duration,
      allocation: MAX_UINT256,
    });
    const latest = await ethers.provider.getBlock("latest");
    const elapsed = BigInt(latest.timestamp);

    expect(elapsed).to.be.lt(duration);
    expect(await wallet.vestedAmount()).to.equal((MAX_UINT256 * elapsed) / duration);
  });

  it("caps a cliff revoke refund at the wallet's actual balance", async function () {
    const [owner, beneficiary] = await ethers.getSigners();
    const allocation = 1_000n;
    const token = await deployToken(allocation);
    const latest = await ethers.provider.getBlock("latest");
    const wallet = await deployWallet({
      beneficiary: beneficiary.address,
      token,
      start: BigInt(latest.timestamp) + 1_000n,
      cliff: 1_000n,
      duration: 2_000n,
      allocation,
    });
    await token.transfer(await wallet.getAddress(), 600n);

    await wallet.connect(owner).revoke();

    expect(await token.balanceOf(owner.address)).to.equal(allocation);
    expect(await token.balanceOf(await wallet.getAddress())).to.equal(0n);
    expect(await wallet.releasable()).to.equal(0n);
    await expect(wallet.connect(beneficiary).release()).to.be.revertedWith("Vesting: revoked");
  });

  it("refunds all unreleased tokens after a partial release", async function () {
    const [owner, beneficiary] = await ethers.getSigners();
    const allocation = 1_000n;
    const token = await deployToken(allocation);
    const latest = await ethers.provider.getBlock("latest");
    const start = BigInt(latest.timestamp) + 10n;
    const wallet = await deployWallet({
      beneficiary: beneficiary.address,
      token,
      start,
      cliff: 0n,
      duration: 1_000n,
      allocation,
    });
    await token.transfer(await wallet.getAddress(), allocation);

    await ethers.provider.send("evm_setNextBlockTimestamp", [Number(start + 500n)]);
    await wallet.connect(beneficiary).release();
    expect(await wallet.released()).to.equal(500n);

    await wallet.connect(owner).revoke();
    expect(await token.balanceOf(owner.address)).to.equal(500n);
    expect(await token.balanceOf(await wallet.getAddress())).to.equal(0n);
  });
});
