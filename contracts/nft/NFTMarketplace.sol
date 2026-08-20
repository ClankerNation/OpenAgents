// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor rafaio1
 * @timestamp 2026-08-20T03:00:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */


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

    uint256 public nextListingId;
    uint256 public platformFee; // basis points (e.g., 250 = 2.5%)
    address public feeRecipient;

    mapping(uint256 => Listing) public listings;

    struct Auction {
        address seller;
        address nftContract;
        uint256 tokenId;
        uint256 startPrice;
        uint256 reservePrice;
        uint256 endTime;
        address highestBidder;
        uint256 highestBid;
        bool active;
        bool settled;
    }

    uint256 public nextAuctionId;
    mapping(uint256 => Auction) public auctions;

    event AuctionCreated(uint256 indexed auctionId, address indexed seller, address nftContract, uint256 tokenId, uint256 startPrice, uint256 reservePrice, uint256 endTime);
    event BidPlaced(uint256 indexed auctionId, address indexed bidder, uint256 amount);
    event AuctionSettled(uint256 indexed auctionId, address indexed winner, uint256 amount);
    event AuctionCancelled(uint256 indexed auctionId);

    event Listed(uint256 indexed listingId, address indexed seller, address nftContract, uint256 tokenId, uint256 price);
    event Sold(uint256 indexed listingId, address indexed buyer, uint256 price);
    event Canceled(uint256 indexed listingId);

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

    /// @notice Create an auction for an NFT.
    /// @param nftContract The ERC721 contract address.
    /// @param tokenId The token ID to auction.
    /// @param startPrice Starting bid amount.
    /// @param reservePrice Minimum price for settlement (0 = no reserve).
    /// @param duration Auction duration in seconds.
    function createAuction(
        address nftContract,
        uint256 tokenId,
        uint256 startPrice,
        uint256 reservePrice,
        uint256 duration
    ) external returns (uint256) {
        IERC721 nft = IERC721(nftContract);
        require(nft.ownerOf(tokenId) == msg.sender, "Not NFT owner");
        require(nft.getApproved(tokenId) == address(this), "Marketplace not approved");
        require(duration > 0, "Invalid duration");
        require(startPrice > 0, "Invalid start price");

        uint256 auctionId = nextAuctionId++;
        auctions[auctionId] = Auction({
            seller: msg.sender,
            nftContract: nftContract,
            tokenId: tokenId,
            startPrice: startPrice,
            reservePrice: reservePrice,
            endTime: block.timestamp + duration,
            highestBidder: address(0),
            highestBid: 0,
            active: true,
            settled: false
        });

        emit AuctionCreated(auctionId, msg.sender, nftContract, tokenId, startPrice, reservePrice, block.timestamp + duration);
        return auctionId;
    }

    /// @notice Place a bid on an active auction.
    /// @param auctionId The auction to bid on.
    /// @dev Bids must exceed current highest bid by at least 5%. Previous bidder is auto-refunded.
    function placeBid(uint256 auctionId) external payable {
        Auction storage auction = auctions[auctionId];
        require(auction.active, "Auction not active");
        require(block.timestamp < auction.endTime, "Auction ended");

        uint256 minBid;
        if (auction.highestBid == 0) {
            minBid = auction.startPrice;
        } else {
            // Must exceed previous bid by 5%
            minBid = auction.highestBid + (auction.highestBid * 5) / 100;
        }
        require(msg.value >= minBid, "Bid too low");

        // Refund previous highest bidder
        if (auction.highestBidder != address(0)) {
            uint256 refund = auction.highestBid;
            auction.highestBidder = address(0);
            auction.highestBid = 0;
            (bool sent, ) = auction.highestBidder.call{value: refund}("");
            require(sent, "Refund failed");
        }

        auction.highestBidder = msg.sender;
        auction.highestBid = msg.value;

        emit BidPlaced(auctionId, msg.sender, msg.value);
    }

    /// @notice Settle an auction after it has ended.
    /// @param auctionId The auction to settle.
    /// @dev Transfers NFT to winner and funds to seller. Enforces reserve price.
    function settleAuction(uint256 auctionId) external {
        Auction storage auction = auctions[auctionId];
        require(auction.active, "Auction not active");
        require(!auction.settled, "Already settled");
        require(block.timestamp >= auction.endTime, "Auction not ended");

        auction.active = false;
        auction.settled = true;

        // Check reserve price
        if (auction.reservePrice > 0 && auction.highestBid < auction.reservePrice) {
            // Reserve not met - return NFT to seller and refund bidder
            if (auction.highestBidder != address(0)) {
                (bool refunded, ) = auction.highestBidder.call{value: auction.highestBid}("");
                require(refunded, "Bidder refund failed");
            }
            emit AuctionCancelled(auctionId);
            return;
        }

        // No bids - cancel
        if (auction.highestBidder == address(0)) {
            emit AuctionCancelled(auctionId);
            return;
        }

        // Transfer NFT to winner
        IERC721(auction.nftContract).transferFrom(auction.seller, auction.highestBidder, auction.tokenId);

        // Calculate fee and transfer proceeds to seller
        uint256 fee = (auction.highestBid * platformFee) / 10000;
        uint256 sellerProceeds = auction.highestBid - fee;

        (bool feeSent, ) = feeRecipient.call{value: fee}("");
        require(feeSent, "Fee transfer failed");

        (bool sellerSent, ) = auction.seller.call{value: sellerProceeds}("");
        require(sellerSent, "Seller transfer failed");

        emit AuctionSettled(auctionId, auction.highestBidder, auction.highestBid);
    }

    /// @notice Cancel an auction (only seller, only if no bids placed).
    /// @param auctionId The auction to cancel.
    function cancelAuction(uint256 auctionId) external {
        Auction storage auction = auctions[auctionId];
        require(auction.active, "Auction not active");
        require(auction.seller == msg.sender, "Not seller");
        require(auction.highestBidder == address(0), "Has bids");

        auction.active = false;
        emit AuctionCancelled(auctionId);
    }

    function getListing(uint256 listingId) external view returns (Listing memory) {
        return listings[listingId];
    }

    function getAuction(uint256 auctionId) external view returns (Auction memory) {
        return auctions[auctionId];
    }
}
