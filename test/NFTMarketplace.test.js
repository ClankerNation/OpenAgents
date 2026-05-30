const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("NFTMarketplace Auctions", function () {
  let nft, marketplace;
  let owner, seller, bidder1, bidder2;
  const platformFee = 250; // 2.5%

  beforeEach(async function () {
    [owner, seller, bidder1, bidder2] = await ethers.getSigners();

    // Deploy Mock NFT
    const MockERC721 = await ethers.getContractFactory("MockERC721");
    nft = await MockERC721.deploy();
    await nft.waitForDeployment();

    // Deploy NFTMarketplace
    const NFTMarketplace = await ethers.getContractFactory("NFTMarketplace");
    marketplace = await NFTMarketplace.deploy(platformFee, owner.address);
    await marketplace.waitForDeployment();
  });

  describe("createAuction", function () {
    it("should create an auction with parameters", async function () {
      const tokenId = await nft.mint.staticCall(seller.address);
      await nft.mint(seller.address);

      await nft.connect(seller).approve(marketplace.target, tokenId);

      const startPrice = ethers.parseEther("1");
      const reservePrice = ethers.parseEther("2");
      const duration = 3600;

      await expect(marketplace.connect(seller).createAuction(
        nft.target,
        tokenId,
        startPrice,
        reservePrice,
        duration
      )).to.emit(marketplace, "AuctionCreated");

      const auction = await marketplace.getAuction(0);
      expect(auction.seller).to.equal(seller.address);
      expect(auction.nftContract).to.equal(nft.target);
      expect(auction.tokenId).to.equal(tokenId);
      expect(auction.startPrice).to.equal(startPrice);
      expect(auction.reservePrice).to.equal(reservePrice);
      expect(auction.duration).to.equal(duration);
      expect(auction.active).to.be.true;
    });
  });

  describe("placeBid & settleAuction", function () {
    let tokenId;
    const startPrice = ethers.parseEther("1");
    const reservePrice = ethers.parseEther("2");
    const duration = 3600;

    beforeEach(async function () {
      tokenId = await nft.mint.staticCall(seller.address);
      await nft.mint(seller.address);
      await nft.connect(seller).approve(marketplace.target, tokenId);

      await marketplace.connect(seller).createAuction(
        nft.target,
        tokenId,
        startPrice,
        reservePrice,
        duration
      );
    });

    it("should reject bids below startPrice", async function () {
      await expect(marketplace.connect(bidder1).placeBid(0, { value: ethers.parseEther("0.9") }))
        .to.be.revertedWith("Bid below start price");
    });

    it("should accept valid first bid and handle bid war increments & refunds", async function () {
      // First bid
      await expect(marketplace.connect(bidder1).placeBid(0, { value: ethers.parseEther("1.1") }))
        .to.emit(marketplace, "BidPlaced")
        .withArgs(0, bidder1.address, ethers.parseEther("1.1"));

      // Bid increment too low (needs >= 1.1 * 1.05 = 1.155)
      await expect(marketplace.connect(bidder2).placeBid(0, { value: ethers.parseEther("1.15") }))
        .to.be.revertedWith("Bid increment too low");

      // Valid bid war bid
      const bidder1BalanceBefore = await ethers.provider.getBalance(bidder1.address);
      await marketplace.connect(bidder2).placeBid(0, { value: ethers.parseEther("1.2") });

      // Verify bidder1 was auto-refunded
      const bidder1BalanceAfter = await ethers.provider.getBalance(bidder1.address);
      expect(bidder1BalanceAfter).to.be.gt(bidder1BalanceBefore);

      const auction = await marketplace.getAuction(0);
      expect(auction.highestBid).to.equal(ethers.parseEther("1.2"));
      expect(auction.highestBidder).to.equal(bidder2.address);
    });

    it("should refund highest bidder and keep NFT with seller if reserve price not met at settlement", async function () {
      await marketplace.connect(bidder1).placeBid(0, { value: ethers.parseEther("1.5") });

      // Warp time past duration
      await ethers.provider.send("evm_increaseTime", [duration + 10]);
      await ethers.provider.send("evm_mine");

      const bidder1BalanceBefore = await ethers.provider.getBalance(bidder1.address);

      // Settle auction (reserve of 2 ETH not met)
      await expect(marketplace.connect(owner).settleAuction(0))
        .to.emit(marketplace, "AuctionSettled")
        .withArgs(0, ethers.ZeroAddress, 0, false);

      // Verify refund
      const bidder1BalanceAfter = await ethers.provider.getBalance(bidder1.address);
      expect(bidder1BalanceAfter).to.be.gt(bidder1BalanceBefore);

      // Seller still owns the NFT
      expect(await nft.ownerOf(tokenId)).to.equal(seller.address);

      const auction = await marketplace.getAuction(0);
      expect(auction.active).to.be.false;
    });

    it("should transfer NFT and distribute funds correctly if reserve met at settlement", async function () {
      await marketplace.connect(bidder1).placeBid(0, { value: ethers.parseEther("2.5") }); // reserve met

      // Warp time past duration
      await ethers.provider.send("evm_increaseTime", [duration + 10]);
      await ethers.provider.send("evm_mine");

      const sellerBalanceBefore = await ethers.provider.getBalance(seller.address);
      const recipientBalanceBefore = await ethers.provider.getBalance(owner.address);

      // Settle auction
      await expect(marketplace.connect(owner).settleAuction(0))
        .to.emit(marketplace, "AuctionSettled")
        .withArgs(0, bidder1.address, ethers.parseEther("2.5"), true);

      // Verify NFT transfer
      expect(await nft.ownerOf(tokenId)).to.equal(bidder1.address);

      // Verify proceeds (2.5 ETH - 2.5% fee = 2.4375 ETH to seller)
      const sellerBalanceAfter = await ethers.provider.getBalance(seller.address);
      expect(sellerBalanceAfter - sellerBalanceBefore).to.equal(ethers.parseEther("2.4375"));

      // Verify platform fee (2.5% of 2.5 ETH = 0.0625 ETH)
      const recipientBalanceAfter = await ethers.provider.getBalance(owner.address);
      // Wait, owner might have paid gas for settleAuction, so we check they received approximately the fee
      expect(recipientBalanceAfter - recipientBalanceBefore).to.be.closeTo(
        ethers.parseEther("0.0625"),
        ethers.parseEther("0.01")
      );
    });
  });
});
