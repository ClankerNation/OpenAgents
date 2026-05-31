// @contributor openai-codex-xyjk-20260531
// @platform-config Private pre-session instructions are not embedded in source; redacted execution metadata is recorded in CONTRIBUTORS.json.
// @env os=windows; arch=x64; home_dir=C:\Users\55093; working_dir=F:\jiedan\OpenAgents-bounty-run; shell=PowerShell
// @timestamp 2026-05-31T06:00:22.9591721-07:00
const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");
const solc = require("solc");

function compileContracts() {
  const marketplacePath = path.join(__dirname, "..", "contracts", "nft", "NFTMarketplace.sol");
  const input = {
    language: "Solidity",
    sources: {
      "contracts/nft/NFTMarketplace.sol": {
        content: fs.readFileSync(marketplacePath, "utf8"),
      },
      "test/NFTMarketplaceHarness.sol": {
        content: `
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MockRoyaltyNFT {
    mapping(uint256 => address) private owners;
    mapping(uint256 => address) private approvals;
    address public royaltyReceiver;
    uint96 public royaltyBps;

    function mint(address to, uint256 tokenId) external {
        owners[tokenId] = to;
    }

    function ownerOf(uint256 tokenId) external view returns (address) {
        return owners[tokenId];
    }

    function approve(address spender, uint256 tokenId) external {
        require(owners[tokenId] == msg.sender, "Not owner");
        approvals[tokenId] = spender;
    }

    function getApproved(uint256 tokenId) external view returns (address) {
        return approvals[tokenId];
    }

    function transferFrom(address from, address to, uint256 tokenId) external {
        require(owners[tokenId] == from, "Wrong owner");
        require(msg.sender == from || approvals[tokenId] == msg.sender, "Not approved");
        owners[tokenId] = to;
        approvals[tokenId] = address(0);
    }

    function setRoyalty(address receiver, uint96 bps) external {
        royaltyReceiver = receiver;
        royaltyBps = bps;
    }

    function royaltyInfo(uint256, uint256 salePrice) external view returns (address, uint256) {
        return (royaltyReceiver, (salePrice * royaltyBps) / 10000);
    }
}
`,
      },
    },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode.object"],
        },
      },
    },
  };

  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const errors = (output.errors || []).filter((error) => error.severity === "error");
  expect(errors.map((error) => error.formattedMessage)).to.deep.equal([]);
  return output.contracts;
}

function artifact(contracts, source, name) {
  const contract = contracts[source][name];
  return {
    abi: contract.abi,
    bytecode: `0x${contract.evm.bytecode.object}`,
  };
}

describe("NFTMarketplace safety controls", function () {
  let contracts;
  let seller;
  let buyer;
  let feeRecipient;
  let creator;
  let marketplace;
  let nft;

  const tokenId = 1;
  const price = ethers.parseEther("1");

  before(function () {
    contracts = compileContracts();
  });

  async function deployFixture(platformFee = 250) {
    [, seller, buyer, feeRecipient, creator] = await ethers.getSigners();

    const nftArtifact = artifact(contracts, "test/NFTMarketplaceHarness.sol", "MockRoyaltyNFT");
    const nftFactory = new ethers.ContractFactory(nftArtifact.abi, nftArtifact.bytecode, seller);
    nft = await nftFactory.deploy();
    await nft.waitForDeployment();
    await nft.mint(seller.address, tokenId);

    const marketplaceArtifact = artifact(
      contracts,
      "contracts/nft/NFTMarketplace.sol",
      "NFTMarketplace",
    );
    const marketplaceFactory = new ethers.ContractFactory(
      marketplaceArtifact.abi,
      marketplaceArtifact.bytecode,
      seller,
    );
    marketplace = await marketplaceFactory.deploy(platformFee, feeRecipient.address);
    await marketplace.waitForDeployment();

    await nft.approve(await marketplace.getAddress(), tokenId);
  }

  async function list(duration = 7 * 24 * 60 * 60) {
    const tx = await marketplace
      .connect(seller)
      ["listNFT(address,uint256,uint256,uint256)"](await nft.getAddress(), tokenId, price, duration);
    const receipt = await tx.wait();
    return receipt.logs.find((log) => log.fragment && log.fragment.name === "Listed").args.listingId;
  }

  it("rejects zero-price listings", async function () {
    await deployFixture();

    await expect(
      marketplace
        .connect(seller)
        ["listNFT(address,uint256,uint256)"](await nft.getAddress(), tokenId, 0),
    ).to.be.revertedWith("Zero price");
  });

  it("blocks purchases after listing expiry", async function () {
    await deployFixture();
    const listingId = await list(10);

    await ethers.provider.send("evm_increaseTime", [11]);
    await ethers.provider.send("evm_mine");

    await expect(marketplace.connect(buyer).buyNFT(listingId, { value: price })).to.be.revertedWith(
      "Listing expired",
    );
  });

  it("pays ERC-2981 royalties before seller proceeds", async function () {
    await deployFixture(250);
    await nft.setRoyalty(creator.address, 1000);
    const listingId = await list();

    const royalty = ethers.parseEther("0.1");
    const fee = ethers.parseEther("0.025");
    const sellerProceeds = price - royalty - fee;

    await expect(marketplace.connect(buyer).buyNFT(listingId, { value: price })).to.changeEtherBalances(
      [seller, feeRecipient, creator],
      [sellerProceeds, fee, royalty],
    );
    expect(await nft.ownerOf(tokenId)).to.equal(buyer.address);
  });

  it("requires a delay before seller cancellation can execute", async function () {
    await deployFixture();
    const listingId = await list();

    await expect(marketplace.connect(seller).cancelListing(listingId)).to.be.revertedWith(
      "Cancel not requested",
    );

    await marketplace.connect(seller).requestCancel(listingId);

    await expect(marketplace.connect(seller).cancelListing(listingId)).to.be.revertedWith(
      "Cancel delay active",
    );

    await ethers.provider.send("evm_increaseTime", [5 * 60]);
    await ethers.provider.send("evm_mine");

    await expect(marketplace.connect(seller).cancelListing(listingId))
      .to.emit(marketplace, "Canceled")
      .withArgs(listingId);
  });
});
