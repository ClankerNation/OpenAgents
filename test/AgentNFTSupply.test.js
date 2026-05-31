const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentNFT supply and metadata safety", function () {
  async function deployAgentNFT() {
    const [owner, alice, bob] = await ethers.getSigners();
    const AgentNFT = await ethers.getContractFactory("AgentNFT");
    const nft = await AgentNFT.deploy("Agent NFT", "AGENT", "ipfs://base/");
    await nft.waitForDeployment();
    return { nft, owner, alice, bob };
  }

  it("rejects zero-address minting", async function () {
    const { nft } = await deployAgentNFT();

    await expect(nft.mint(ethers.ZeroAddress, "ipfs://bad")).to.be.revertedWith("Mint to zero");
  });

  it("reverts tokenURI for nonexistent tokens", async function () {
    const { nft } = await deployAgentNFT();

    await expect(nft.tokenURI(42)).to.be.revertedWith("Token does not exist");
  });

  it("batch mints to recipients and preserves per-token URIs", async function () {
    const { nft, alice, bob } = await deployAgentNFT();

    await nft.batchMint(
      [alice.address, bob.address],
      ["ipfs://alice", "ipfs://bob"]
    );

    expect(await nft.totalSupply()).to.equal(2n);
    expect(await nft.ownerOf(0)).to.equal(alice.address);
    expect(await nft.ownerOf(1)).to.equal(bob.address);
    expect(await nft.tokenURI(0)).to.equal("ipfs://alice");
    expect(await nft.tokenURI(1)).to.equal("ipfs://bob");
    expect(await nft.balanceOf(alice.address)).to.equal(1n);
    expect(await nft.balanceOf(bob.address)).to.equal(1n);
  });

  it("rejects batch mint length mismatch", async function () {
    const { nft, alice, bob } = await deployAgentNFT();

    await expect(
      nft.batchMint([alice.address, bob.address], ["ipfs://alice"])
    ).to.be.revertedWith("Length mismatch");
  });

  it("enforces MAX_SUPPLY preflight for batch mint", async function () {
    const { nft, alice, bob } = await deployAgentNFT();
    const maxSupply = Number(await nft.MAX_SUPPLY());
    const nextTokenIdSlot = "0x04";
    const nearCap = ethers.toBeHex(maxSupply - 1, 32);

    await ethers.provider.send("hardhat_setStorageAt", [
      await nft.getAddress(),
      nextTokenIdSlot,
      nearCap,
    ]);

    await expect(
      nft.batchMint([alice.address, bob.address], ["ipfs://alice", "ipfs://bob"])
    ).to.be.revertedWith("Max supply exceeded");
    expect(await nft.totalSupply()).to.equal(BigInt(maxSupply - 1));
  });
});
