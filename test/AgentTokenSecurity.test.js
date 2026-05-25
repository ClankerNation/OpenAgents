const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentToken security hardening", function () {
  const parse = ethers.parseEther;

  let owner;
  let user;
  let spender;
  let token;

  async function deployToken(initialSupply = parse("1000")) {
    [owner, user, spender] = await ethers.getSigners();
    const AgentToken = await ethers.getContractFactory("AgentToken");
    token = await AgentToken.deploy("Agent Token", "AGENT", initialSupply);
    await token.waitForDeployment();
  }

  beforeEach(async function () {
    await deployToken();
  });

  async function signPermit(tokenOwner, tokenSpender, value, deadline) {
    const chainId = (await ethers.provider.getNetwork()).chainId;
    const domain = {
      name: "Agent Token",
      version: "1",
      chainId,
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
    const message = {
      owner: tokenOwner.address,
      spender: tokenSpender.address,
      value,
      nonce: await token.nonces(tokenOwner.address),
      deadline,
    };
    return ethers.Signature.from(await tokenOwner.signTypedData(domain, types, message));
  }

  it("restricts minting to the owner", async function () {
    await expect(token.connect(user).mint(user.address, parse("1"))).to.be.revertedWith(
      "AgentToken: not owner"
    );

    await token.mint(user.address, parse("1"));
    expect(await token.balanceOf(user.address)).to.equal(parse("1"));
  });

  it("caps initial and minted supply", async function () {
    const cap = await token.MAX_SUPPLY();
    const AgentToken = await ethers.getContractFactory("AgentToken");

    await expect(AgentToken.deploy("Agent Token", "AGENT", cap + 1n)).to.be.revertedWith(
      "AgentToken: cap exceeded"
    );

    const remaining = cap - (await token.totalSupply());
    await token.mint(user.address, remaining);
    expect(await token.totalSupply()).to.equal(cap);
    await expect(token.mint(user.address, 1n)).to.be.revertedWith("AgentToken: cap exceeded");
  });

  it("rejects expired permits before consuming the nonce", async function () {
    const latestBlock = await ethers.provider.getBlock("latest");
    const deadline = latestBlock.timestamp - 1;
    const signature = await signPermit(owner, spender, parse("1"), deadline);

    await expect(
      token.permit(owner.address, spender.address, parse("1"), deadline, signature.v, signature.r, signature.s)
    ).to.be.revertedWith("AgentToken: expired permit");
    expect(await token.nonces(owner.address)).to.equal(0n);
  });

  it("accepts valid permits and supports burning", async function () {
    const latestBlock = await ethers.provider.getBlock("latest");
    const deadline = latestBlock.timestamp + 3600;
    const signature = await signPermit(owner, spender, parse("2"), deadline);

    await token.permit(owner.address, spender.address, parse("2"), deadline, signature.v, signature.r, signature.s);
    expect(await token.allowance(owner.address, spender.address)).to.equal(parse("2"));
    expect(await token.nonces(owner.address)).to.equal(1n);

    const supplyBefore = await token.totalSupply();
    await token.burn(parse("10"));
    expect(await token.totalSupply()).to.equal(supplyBefore - parse("10"));
  });
});
