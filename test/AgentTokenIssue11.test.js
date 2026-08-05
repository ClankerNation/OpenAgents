const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentToken security hardening", function () {
  const MAX_SUPPLY = 1_000_000_000n * 10n ** 18n;

  async function deploy(initialSupply = 1_000n) {
    const [owner, other, spender] = await ethers.getSigners();
    const AgentToken = await ethers.getContractFactory("AgentToken");
    const token = await AgentToken.deploy("Agent Token", "AGT", initialSupply);
    await token.waitForDeployment();
    return { token, owner, other, spender };
  }

  it("caps initial supply and restricts minting to the owner", async function () {
    const AgentToken = await ethers.getContractFactory("AgentToken");
    await expect(AgentToken.deploy("Agent Token", "AGT", MAX_SUPPLY + 1n)).to.be.revertedWith(
      "AgentToken: initial supply exceeds max"
    );

    const { token, owner, other } = await deploy();
    await expect(token.connect(other).mint(other.address, 1n)).to.be.revertedWith(
      "AgentToken: not owner"
    );

    await token.connect(owner).mint(other.address, MAX_SUPPLY - 1_000n);
    expect(await token.totalSupply()).to.equal(MAX_SUPPLY);
    await expect(token.mint(owner.address, 1n)).to.be.revertedWith(
      "AgentToken: exceeds max supply"
    );
  });

  it("retains burn and burnFrom functionality", async function () {
    const { token, owner, other } = await deploy(100n);

    await token.burn(25n);
    expect(await token.totalSupply()).to.equal(75n);

    await token.approve(other.address, 10n);
    await token.connect(other).burnFrom(owner.address, 10n);
    expect(await token.totalSupply()).to.equal(65n);
  });

  it("accepts a valid permit and advances the nonce only after verification", async function () {
    const { token, owner, spender } = await deploy();
    const network = await ethers.provider.getNetwork();
    const latest = await ethers.provider.getBlock("latest");
    const deadline = BigInt(latest.timestamp) + 3_600n;
    const value = 250n;
    const domain = {
      name: "Agent Token",
      version: "1",
      chainId: network.chainId,
      verifyingContract: await token.getAddress(),
    };
    const types = {
      Permit: [
        { name: "owner", type: "address" },
        { name: "spender", type: "address" },
        { name: "value", type: "uint256" },
        { name: "nonce", type: "uint256" },
        { name: "deadline", type: "uint256" },
      ],
    };
    const signature = await owner.signTypedData(domain, types, {
      owner: owner.address,
      spender: spender.address,
      value,
      nonce: 0n,
      deadline,
    });
    const { v, r, s } = ethers.Signature.from(signature);

    await token.connect(spender).permit(owner.address, spender.address, value, deadline, v, r, s);
    expect(await token.allowance(owner.address, spender.address)).to.equal(value);
    expect(await token.nonces(owner.address)).to.equal(1n);
  });

  it("rejects expired permits before consuming a nonce", async function () {
    const { token, owner, spender } = await deploy();
    const latest = await ethers.provider.getBlock("latest");
    const expired = BigInt(latest.timestamp) - 1n;

    await expect(
      token.connect(spender).permit(
        owner.address,
        spender.address,
        1n,
        expired,
        27,
        ethers.ZeroHash,
        ethers.ZeroHash
      )
    ).to.be.revertedWith("AgentToken: permit expired");
    expect(await token.nonces(owner.address)).to.equal(0n);
  });
});
