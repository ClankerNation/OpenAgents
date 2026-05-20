const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentToken", function () {
  async function deployToken() {
    const [owner] = await ethers.getSigners();
    const AgentToken = await ethers.getContractFactory("AgentToken");
    const token = await AgentToken.deploy("Agent Token", "AGENT", ethers.parseEther("1000"));
    await token.waitForDeployment();
    return { owner, token };
  }

  function expectedDomainSeparator(name, chainId, verifyingContract) {
    return ethers.TypedDataEncoder.hashDomain({
      name,
      version: "1",
      chainId,
      verifyingContract,
    });
  }

  it("returns a domain separator bound to the current chain id", async function () {
    const { token } = await deployToken();
    const tokenAddress = await token.getAddress();
    const { chainId } = await ethers.provider.getNetwork();

    expect(await token.DOMAIN_SEPARATOR()).to.equal(
      expectedDomainSeparator("Agent Token", chainId, tokenAddress),
    );
  });

  it("uses a different domain separator for a different chain id", async function () {
    const { token } = await deployToken();
    const tokenAddress = await token.getAddress();
    const { chainId } = await ethers.provider.getNetwork();
    const original = await token.DOMAIN_SEPARATOR();

    const forkChainId = Number(chainId) + 1;
    const forkSeparator = expectedDomainSeparator("Agent Token", forkChainId, tokenAddress);

    expect(forkSeparator).to.not.equal(original);
    expect(forkSeparator).to.equal(
      expectedDomainSeparator("Agent Token", forkChainId, tokenAddress),
    );
  });
});
