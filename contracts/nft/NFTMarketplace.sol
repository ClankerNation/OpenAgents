// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC721 {
    function ownerOf(uint256 tokenId) external view returns (address);
    function transferFrom(address from, address to, uint256 tokenId) external;
    function getApproved(uint256 tokenId) external view returns (address);
}

/// @title NFTMarketplace
/// @notice Decentralized marketplace for listing, buying, and canceling NFT sales
/// @dev Supports any ERC721-compliant NFT contract
contract NFTMarketplace {
    struct Listing {
        address seller;
        address nftContract;
        uint256 tokenId;
        uint256 price;
        bool active;
    }

    struct Auction {
        address seller;
        address nftContract;
        uint256 tokenId;
        uint256 startPrice;
        uint256 reservePrice;
        uint256 endTime;
        address highestBidder;
        uint256 highestBid;
        bool settled;
    }

    uint256 public nextListingId;
    uint256 public nextAuctionId;
    uint256 public platformFee; // basis points (e.g., 250 = 2.5%)
    address public feeRecipient;

    mapping(uint256 => Listing) public listings;
    mapping(uint256 => Auction) public auctions;

    event Listed(uint256 indexed listingId, address indexed seller, address nftContract, uint256 tokenId, uint256 price);
    event Sold(uint256 indexed listingId, address indexed buyer, uint256 price);
    event Canceled(uint256 indexed listingId);
    event AuctionCreated(uint256 indexed auctionId, address indexed seller, address nftContract, uint256 tokenId, uint256 startPrice, uint256 reservePrice, uint256 endTime);
    event BidPlaced(uint256 indexed auctionId, address indexed bidder, uint256 amount);
    event AuctionSettled(uint256 indexed auctionId, address indexed winner, uint256 amount);

    constructor(uint256 _platformFee, address _feeRecipient) {
        platformFee = _platformFee;
        feeRecipient = _feeRecipient;
    }

    // BUG: Price can be zero — allows listings with price 0, meaning NFTs can
    // be "sold" for free and the platform earns no fee
    function listNFT(address nftContract, uint256 tokenId, uint256 price) external returns (uint256) {
        IERC721 nft = IERC721(nftContract);
        require(nft.ownerOf(tokenId) == msg.sender, "Not NFT owner");
        require(
            nft.getApproved(tokenId) == address(this),
            "Marketplace not approved"
        );

        uint256 listingId = nextListingId++;
        listings[listingId] = Listing({
            seller: msg.sender,
            nftContract: nftContract,
            tokenId: tokenId,
            price: price,
            active: true
        });

        emit Listed(listingId, msg.sender, nftContract, tokenId, price);
        return listingId;
    }

    // BUG: Seller can front-run cancel after buyer's tx is in mempool —
    // seller sees buy tx, quickly cancels to re-list at higher price (no commit-reveal)
    // BUG: No royalty payment — original creator receives nothing on secondary sales,
    // violating ERC-2981 royalty standard expectations
    function buyNFT(uint256 listingId) external payable {
        Listing storage listing = listings[listingId];
        require(listing.active, "Not active");
        require(msg.value == listing.price, "Wrong price");

        listing.active = false;

        uint256 fee = (msg.value * platformFee) / 10000;
        uint256 sellerProceeds = msg.value - fee;

        IERC721(listing.nftContract).transferFrom(
            listing.seller,
            msg.sender,
            listing.tokenId
        );

        (bool feeSent, ) = feeRecipient.call{value: fee}("");
        require(feeSent, "Fee transfer failed");

        (bool sellerSent, ) = listing.seller.call{value: sellerProceeds}("");
        require(sellerSent, "Seller transfer failed");

        emit Sold(listingId, msg.sender, msg.value);
    }

    function cancelListing(uint256 listingId) external {
        Listing storage listing = listings[listingId];
        require(listing.active, "Not active");
        require(listing.seller == msg.sender, "Not seller");

        listing.active = false;
        emit Canceled(listingId);
    }

    function getListing(uint256 listingId) external view returns (Listing memory) {
        return listings[listingId];
    }

    /// @notice Create an auction-style listing for an NFT
    /// @param nftContract The ERC721 contract address
    /// @param tokenId The token ID to auction
    /// @param startPrice Starting bid amount in wei
    /// @param reservePrice Minimum acceptable bid (0 = no reserve)
    /// @param duration Auction duration in seconds
    /// @return auctionId The created auction identifier
    function createAuction(
        address nftContract,
        uint256 tokenId,
        uint256 startPrice,
        uint256 reservePrice,
        uint256 duration
    ) external returns (uint256 auctionId) {
        IERC721 nft = IERC721(nftContract);
        require(nft.ownerOf(tokenId) == msg.sender, "Not NFT owner");
        require(nft.getApproved(tokenId) == address(this), "Marketplace not approved");
        require(startPrice > 0, "Start price must be > 0");
        require(duration > 0, "Duration must be > 0");

        auctionId = nextAuctionId++;
        auctions[auctionId] = Auction({
            seller: msg.sender,
            nftContract: nftContract,
            tokenId: tokenId,
            startPrice: startPrice,
            reservePrice: reservePrice,
            endTime: block.timestamp + duration,
            highestBidder: address(0),
            highestBid: 0,
            settled: false
        });

        emit AuctionCreated(auctionId, msg.sender, nftContract, tokenId, startPrice, reservePrice, block.timestamp + duration);
        return auctionId;
    }

    /// @notice Place a bid on an active auction
    /// @param auctionId The auction to bid on
    function placeBid(uint256 auctionId) external payable {
        Auction storage auction = auctions[auctionId];
        require(block.timestamp < auction.endTime, "Auction ended");
        require(!auction.settled, "Already settled");

        uint256 minBid = auction.highestBid > 0
            ? auction.highestBid + (auction.highestBid * 5 / 100) // 5% increment
            : auction.startPrice;
        require(msg.value >= minBid, "Bid too low");

        // Refund previous highest bidder
        if (auction.highestBidder != address(0)) {
            (bool refunded, ) = auction.highestBidder.call{value: auction.highestBid}("");
            require(refunded, "Refund failed");
        }

        auction.highestBidder = msg.sender;
        auction.highestBid = msg.value;

        emit BidPlaced(auctionId, msg.sender, msg.value);
    }

    /// @notice Settle an expired auction, transferring NFT to winner and funds to seller
    /// @param auctionId The auction to settle
    function settleAuction(uint256 auctionId) external {
        Auction storage auction = auctions[auctionId];
        require(block.timestamp >= auction.endTime, "Auction not ended");
        require(!auction.settled, "Already settled");

        auction.settled = true;

        // If no bids or reserve not met, return NFT to seller
        if (auction.highestBidder == address(0) || (auction.reservePrice > 0 && auction.highestBid < auction.reservePrice)) {
            IERC721(auction.nftContract).transferFrom(address(this), auction.seller, auction.tokenId);
            emit AuctionSettled(auctionId, auction.seller, 0);
            return;
        }

        // Transfer NFT to winner
        IERC721(auction.nftContract).transferFrom(address(this), auction.highestBidder, auction.tokenId);

        // Calculate fees and proceeds
        uint256 fee = (auction.highestBid * platformFee) / 10000;
        uint256 sellerProceeds = auction.highestBid - fee;

        (bool feeSent, ) = feeRecipient.call{value: fee}("");
        require(feeSent, "Fee transfer failed");

        (bool sellerSent, ) = auction.seller.call{value: sellerProceeds}("");
        require(sellerSent, "Seller transfer failed");

        emit AuctionSettled(auctionId, auction.highestBidder, auction.highestBid);
    }

    /// @notice Get auction details
    /// @param auctionId The auction to query
    function getAuction(uint256 auctionId) external view returns (Auction memory) {
        return auctions[auctionId];
    }
}
