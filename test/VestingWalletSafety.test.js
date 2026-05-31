const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

function loadArtifact(name) {
  const base = path.join(__dirname, "..", ".codex-vesting-solc");
  const abiPath = path.join(base, `${name}.abi`);
  const binPath = path.join(base, `${name}.bin`);
  if (!fs.existsSync(abiPath) || !fs.existsSync(binPath)) {
    throw new Error("Missing solcjs artifacts. Run the solcjs verification command before this test.");
  }
  return {
    abi: JSON.parse(fs.readFileSync(abiPath, "utf8")),
    bytecode: `0x${fs.readFileSync(binPath, "utf8").trim()}`,
  };
}

describe("VestingWallet safety", function () {
  const VESTING_ARTIFACT = "contracts_token_VestingWallet_sol_VestingWallet";
  const TOKEN_ARTIFACT = "test_mocks_MockERC20_sol_MockERC20";
  const ONE_BILLION_TOKENS = ethers.parseUnits("1000000000", 18);
  const DAY = 24 * 60 * 60;

  async function deployToken(owner) {
    const artifact = loadArtifact(TOKEN_ARTIFACT);
    const factory = new ethers.ContractFactory(artifact.abi, artifact.bytecode, owner);
    const token = await factory.deploy();
    await token.waitForDeployment();
    return token;
  }

  async function deployVesting({ beneficiary, token, start, cliff, duration, allocation, revocable = true, owner }) {
    const artifact = loadArtifact(VESTING_ARTIFACT);
    const factory = new ethers.ContractFactory(artifact.abi, artifact.bytecode, owner);
    const vesting = await factory.deploy(
      beneficiary,
      await token.getAddress(),
      start,
      cliff,
      duration,
      allocation,
      revocable
    );
    await vesting.waitForDeployment();
    return vesting;
  }

  async function now() {
    const block = await ethers.provider.getBlock("latest");
    return block.timestamp;
  }

  it("rejects zero-address beneficiaries", async function () {
    const [owner] = await ethers.getSigners();
    const token = await deployToken(owner);
    const timestamp = await now();

    await expect(
      deployVesting({
        beneficiary: ethers.ZeroAddress,
        token,
        start: timestamp,
        cliff: DAY,
        duration: 365 * DAY,
        allocation: ONE_BILLION_TOKENS,
        owner,
      })
    ).to.be.revertedWith("Vesting: zero beneficiary");
  });

  it("vests a 1B token allocation without multiplication overflow", async function () {
    const [owner, beneficiary] = await ethers.getSigners();
    const token = await deployToken(owner);
    const start = (await now()) + 10;
    const duration = 365 * DAY;
    const vesting = await deployVesting({
      beneficiary: beneficiary.address,
      token,
      start,
      cliff: 0,
      duration,
      allocation: ONE_BILLION_TOKENS,
      owner,
    });

    await ethers.provider.send("evm_setNextBlockTimestamp", [start + Math.floor(duration / 2)]);
    await ethers.provider.send("evm_mine", []);

    const vested = await vesting.vestedAmount();
    expect(vested).to.equal(ONE_BILLION_TOKENS / 2n);
  });

  it("refunds unreleased allocation during cliff revoke", async function () {
    const [owner, beneficiary] = await ethers.getSigners();
    const token = await deployToken(owner);
    const start = (await now()) + 10;
    const allocation = ethers.parseUnits("1000", 18);
    const vesting = await deployVesting({
      beneficiary: beneficiary.address,
      token,
      start,
      cliff: 30 * DAY,
      duration: 365 * DAY,
      allocation,
      owner,
    });
    await token.mint(await vesting.getAddress(), allocation);

    const ownerBefore = await token.balanceOf(owner.address);
    await vesting.revoke();

    expect(await token.balanceOf(owner.address)).to.equal(ownerBefore + allocation);
    expect(await token.balanceOf(await vesting.getAddress())).to.equal(0n);
    expect(await vesting.revoked()).to.equal(true);
    expect(await vesting.releasable()).to.equal(0n);
  });

  it("refunds total allocation minus released tokens on revoke", async function () {
    const [owner, beneficiary] = await ethers.getSigners();
    const token = await deployToken(owner);
    const start = (await now()) + 10;
    const duration = 1000;
    const allocation = ethers.parseUnits("1000", 18);
    const vesting = await deployVesting({
      beneficiary: beneficiary.address,
      token,
      start,
      cliff: 0,
      duration,
      allocation,
      owner,
    });
    await token.mint(await vesting.getAddress(), allocation);

    await ethers.provider.send("evm_setNextBlockTimestamp", [start + Math.floor(duration / 4)]);
    await ethers.provider.send("evm_mine", []);
    await vesting.connect(beneficiary).release();
    const released = await vesting.released();

    const ownerBefore = await token.balanceOf(owner.address);
    await vesting.revoke();

    expect(await token.balanceOf(owner.address)).to.equal(ownerBefore + allocation - released);
    expect(await token.balanceOf(await vesting.getAddress())).to.equal(0n);
  });
});
