const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentNFT", function () {
  let agentNFT;
  let owner, alice, bob, charlie;

  beforeEach(async function () {
    [owner, alice, bob, charlie] = await ethers.getSigners();

    const AgentNFT = await ethers.getContractFactory("AgentNFT");
    agentNFT = await AgentNFT.deploy("Agent", "AGNT", "https://metadata.example/");
    await agentNFT.waitForDeployment();
  });

  // ========== Basic minting ==========

  it("should mint a token and assign correct owner", async function () {
    await agentNFT.mint(alice.address, "ipfs://alice-metadata");

    expect(await agentNFT.ownerOf(0)).to.equal(alice.address);
    expect(await agentNFT.balanceOf(alice.address)).to.equal(1);
    expect(await agentNFT.totalSupply()).to.equal(1);
  });

  it("should emit Transfer event on mint", async function () {
    await expect(agentNFT.mint(alice.address, "ipfs://alice"))
      .to.emit(agentNFT, "Transfer")
      .withArgs(ethers.ZeroAddress, alice.address, 0);
  });

  it("should increment token IDs sequentially", async function () {
    await agentNFT.mint(alice.address, "");
    await agentNFT.mint(bob.address, "");
    await agentNFT.mint(charlie.address, "");

    expect(await agentNFT.ownerOf(0)).to.equal(alice.address);
    expect(await agentNFT.ownerOf(1)).to.equal(bob.address);
    expect(await agentNFT.ownerOf(2)).to.equal(charlie.address);
    expect(await agentNFT.totalSupply()).to.equal(3);
  });

  // ========== tokenURI ==========

  it("should return custom URI when token has a stored URI", async function () {
    await agentNFT.mint(alice.address, "ipfs://custom-uri");
    expect(await agentNFT.tokenURI(0)).to.equal("ipfs://custom-uri");
  });

  it("should fall back to baseURI + tokenId when no custom URI is stored", async function () {
    await agentNFT.setBaseURI("https://metadata.example/");
    await agentNFT.mint(alice.address, "");
    expect(await agentNFT.tokenURI(0)).to.equal("https://metadata.example/0");
  });

  it("should revert tokenURI for non-existent token (never minted)", async function () {
    await expect(agentNFT.tokenURI(42)).to.be.revertedWith("Token does not exist");
  });

  it("should revert tokenURI for token ID beyond current supply", async function () {
    await agentNFT.mint(alice.address, "ipfs://token-0");
    // token 0 exists, token 1 does not
    expect(await agentNFT.tokenURI(0)).to.equal("ipfs://token-0");
    await expect(agentNFT.tokenURI(1)).to.be.revertedWith("Token does not exist");
  });

  // ========== Zero address mint rejection ==========

  it("should revert mint to zero address", async function () {
    await expect(
      agentNFT.mint(ethers.ZeroAddress, "ipfs://zero")
    ).to.be.revertedWith("Mint to zero address");
  });

  // ========== MAX_SUPPLY enforcement ==========

  it("should enforce MAX_SUPPLY and reject mints beyond cap", async function () {
    const BATCH_SIZE = 1000;
    const BATCHES = 10; // 10 * 1000 = 10000 = MAX_SUPPLY

    for (let round = 0; round < BATCHES; round++) {
      const recipients = new Array(BATCH_SIZE).fill(alice.address);
      const uris = new Array(BATCH_SIZE).fill("");
      await agentNFT.batchMint(recipients, uris);
    }

    expect(await agentNFT.totalSupply()).to.equal(10000);

    await expect(
      agentNFT.mint(bob.address, "ipfs://beyond-cap")
    ).to.be.revertedWith("Max supply reached");
  });

  // ========== batchMint ==========

  it("should batch mint multiple tokens with correct ownership and URIs", async function () {
    const recipients = [alice.address, bob.address, charlie.address];
    const uris = ["ipfs://a", "ipfs://b", "ipfs://c"];

    await agentNFT.batchMint(recipients, uris);

    expect(await agentNFT.totalSupply()).to.equal(3);
    expect(await agentNFT.ownerOf(0)).to.equal(alice.address);
    expect(await agentNFT.ownerOf(1)).to.equal(bob.address);
    expect(await agentNFT.ownerOf(2)).to.equal(charlie.address);
    expect(await agentNFT.tokenURI(0)).to.equal("ipfs://a");
    expect(await agentNFT.tokenURI(1)).to.equal("ipfs://b");
    expect(await agentNFT.tokenURI(2)).to.equal("ipfs://c");
    expect(await agentNFT.balanceOf(alice.address)).to.equal(1);
    expect(await agentNFT.balanceOf(bob.address)).to.equal(1);
    expect(await agentNFT.balanceOf(charlie.address)).to.equal(1);
  });

  it("batchMint should assign sequential token IDs across calls", async function () {
    await agentNFT.batchMint([alice.address, bob.address], ["", ""]);
    expect(await agentNFT.ownerOf(0)).to.equal(alice.address);
    expect(await agentNFT.ownerOf(1)).to.equal(bob.address);

    await agentNFT.batchMint([charlie.address], [""]);
    expect(await agentNFT.ownerOf(2)).to.equal(charlie.address);
    expect(await agentNFT.totalSupply()).to.equal(3);
  });

  it("should revert batchMint on empty batch", async function () {
    await expect(
      agentNFT.batchMint([], [])
    ).to.be.revertedWith("Empty batch");
  });

  it("should revert batchMint on length mismatch", async function () {
    await expect(
      agentNFT.batchMint([alice.address, bob.address], ["only-one-uri"])
    ).to.be.revertedWith("Length mismatch");
  });

  it("should revert batchMint with zero address in batch", async function () {
    const recipients = [alice.address, ethers.ZeroAddress];
    const uris = ["ipfs://ok", "ipfs://bad"];

    await expect(
      agentNFT.batchMint(recipients, uris)
    ).to.be.revertedWith("Mint to zero address");
  });

  it("should revert batchMint when batch exceeds remaining supply", async function () {
    // Fill to 9999 — almost at the cap
    const BATCH_SIZE = 1000;
    for (let round = 0; round < 9; round++) {
      const recipients = new Array(BATCH_SIZE).fill(alice.address);
      const uris = new Array(BATCH_SIZE).fill("");
      await agentNFT.batchMint(recipients, uris);
    }

    const recipients = new Array(999).fill(bob.address);
    const uris = new Array(999).fill("");
    await agentNFT.batchMint(recipients, uris);

    expect(await agentNFT.totalSupply()).to.equal(9999);

    // 2 tokens would exceed MAX_SUPPLY
    await expect(
      agentNFT.batchMint([alice.address, bob.address], ["a", "b"])
    ).to.be.revertedWith("Batch exceeds max supply");
  });

  it("should allow batchMint up to exact MAX_SUPPLY boundary", async function () {
    const BATCH_SIZE = 1000;
    for (let round = 0; round < 9; round++) {
      const recipients = new Array(BATCH_SIZE).fill(alice.address);
      const uris = new Array(BATCH_SIZE).fill("");
      await agentNFT.batchMint(recipients, uris);
    }

    // Fill exactly to 10000
    const recipients = new Array(1000).fill(bob.address);
    const uris = new Array(1000).fill("");
    await agentNFT.batchMint(recipients, uris);

    expect(await agentNFT.totalSupply()).to.equal(10000);
    expect(await agentNFT.ownerOf(9999)).to.equal(bob.address);
  });

  // ========== Access control ==========

  it("should reject mint from non-owner", async function () {
    await expect(
      agentNFT.connect(alice).mint(alice.address, "ipfs://unauthorized")
    ).to.be.revertedWith("Not owner");
  });

  it("should reject batchMint from non-owner", async function () {
    await expect(
      agentNFT.connect(alice).batchMint([alice.address], ["ipfs://unauthorized"])
    ).to.be.revertedWith("Not owner");
  });

  // ========== Transfer + tokenURI ==========

  it("should still resolve tokenURI after token transfer", async function () {
    await agentNFT.mint(alice.address, "ipfs://transferable");

    await agentNFT.connect(alice).transferFrom(alice.address, bob.address, 0);

    expect(await agentNFT.ownerOf(0)).to.equal(bob.address);
    expect(await agentNFT.tokenURI(0)).to.equal("ipfs://transferable");
  });
});
