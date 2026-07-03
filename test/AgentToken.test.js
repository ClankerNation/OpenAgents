const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentToken", function () {
  let agentToken, owner, spender;

  beforeEach(async function () {
    [owner, spender] = await ethers.getSigners();

    const AgentToken = await ethers.getContractFactory("AgentToken");
    agentToken = await AgentToken.deploy("AgentToken", "AGENT", ethers.utils.parseEther("1000000"));
    await agentToken.deployed();
  });

  it("should return a domain separator", async function () {
    const separator = await agentToken.DOMAIN_SEPARATOR();
    expect(separator).to.not.equal(ethers.constants.Zero);
  });

  it("should recompute domain separator after chain ID change", async function () {
    const originalSeparator = await agentToken.DOMAIN_SEPARATOR();
    const newChainId = (await ethers.provider.getNetwork()).chainId + 1;
    await ethers.provider.send("hardhat_setChainId", [newChainId]);
    await ethers.provider.send("evm_mine");

    const newSeparator = await agentToken.DOMAIN_SEPARATOR();
    expect(newSeparator).to.not.equal(originalSeparator);
  });

  it("should cache domain separator when chain ID is unchanged", async function () {
    const separator1 = await agentToken.DOMAIN_SEPARATOR();
    const separator2 = await agentToken.DOMAIN_SEPARATOR();
    expect(separator1).to.equal(separator2);
  });
});
