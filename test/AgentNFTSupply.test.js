const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentNFT supply and metadata guards", function () {
  let owner, alice, bob, carol;
  let agentNFT, agentNFTAddress;

  beforeEach(async function () {
    [owner, alice, bob, carol] = await ethers.getSigners();

    const AgentNFT = await ethers.getContractFactory("AgentNFT");
    agentNFT = await AgentNFT.deploy("Agent NFT", "AGENT", "ipfs://agents/");
    await agentNFT.waitForDeployment();
    agentNFTAddress = await agentNFT.getAddress();
  });

  it("rejects zero-address minting", async function () {
    await expect(agentNFT.mint(ethers.ZeroAddress, "ipfs://agent-0")).to.be.revertedWith("Mint to zero");
  });

  it("reverts tokenURI for nonexistent tokens", async function () {
    await expect(agentNFT.tokenURI(0)).to.be.revertedWith("Nonexistent token");
  });

  it("mints batches and stores token-specific URIs", async function () {
    const tx = await agentNFT.batchMint(
      [alice.address, bob.address, carol.address],
      ["ipfs://agent-a", "ipfs://agent-b", ""]
    );

    await expect(tx).to.emit(agentNFT, "Transfer").withArgs(ethers.ZeroAddress, alice.address, 0);
    await expect(tx).to.emit(agentNFT, "Transfer").withArgs(ethers.ZeroAddress, bob.address, 1);
    await expect(tx).to.emit(agentNFT, "Transfer").withArgs(ethers.ZeroAddress, carol.address, 2);

    expect(await agentNFT.totalSupply()).to.equal(3);
    expect(await agentNFT.balanceOf(alice.address)).to.equal(1);
    expect(await agentNFT.tokenURI(0)).to.equal("ipfs://agent-a");
    expect(await agentNFT.tokenURI(2)).to.equal("ipfs://agents/2");
  });

  it("prevents minting beyond MAX_SUPPLY", async function () {
    const maxSupply = await agentNFT.MAX_SUPPLY();
    const nextTokenIdSlot = ethers.toBeHex(4, 32);

    await ethers.provider.send("hardhat_setStorageAt", [
      agentNFTAddress,
      nextTokenIdSlot,
      ethers.toBeHex(maxSupply, 32),
    ]);

    await expect(agentNFT.mint(alice.address, "ipfs://overflow")).to.be.revertedWith("Max supply reached");

    await ethers.provider.send("hardhat_setStorageAt", [
      agentNFTAddress,
      nextTokenIdSlot,
      ethers.toBeHex(maxSupply - 1n, 32),
    ]);

    await expect(
      agentNFT.batchMint([alice.address, bob.address], ["ipfs://a", "ipfs://b"])
    ).to.be.revertedWith("Max supply exceeded");
  });
});
