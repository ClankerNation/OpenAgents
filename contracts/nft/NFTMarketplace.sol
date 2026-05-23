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

    uint256 public nextListingId;
    uint256 public nextAuctionId;
    uint256 public platformFee; // basis points (e.g., 250 = 2.5%)
    address public feeRecipient;
    uint256 public constant MIN_BID_INCREMENT = 500; // 5% in basis points

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
    }

    mapping(uint256 => Auction) public auctions;

    event Listed(uint256 indexed listingId, address indexed seller, address nftContract, uint256 tokenId, uint256 price);
    event Sold(uint256 indexed listingId, address indexed buyer, uint256 price);
    event Canceled(uint256 indexed listingId);
    event AuctionCreated(uint256 indexed auctionId, address indexed seller, uint256 startPrice, uint256 reservePrice, uint256 endTime);
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

    function createAuction(
        address nftContract,
        uint256 tokenId,
        uint256 startPrice,
        uint256 reservePrice,
        uint256 duration
    ) external returns (uint256) {
        IERC721 nft = IERC721(nftContract);
        require(nft.ownerOf(tokenId) == msg.sender, "Not NFT owner");
        require(nft.getApproved(tokenId) == address(this), "Not approved");
        require(startPrice > 0, "Zero start price");
        require(reservePrice >= startPrice, "Reserve below start");
        require(duration >= 1 hours && duration <= 7 days, "Invalid duration");

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
            active: true
        });

        emit AuctionCreated(auctionId, msg.sender, startPrice, reservePrice, block.timestamp + duration);
        return auctionId;
    }

    function placeBid(uint256 auctionId) external payable {
        Auction storage auc = auctions[auctionId];
        require(auc.active, "Auction ended");
        require(block.timestamp < auc.endTime, "Auction expired");
        require(msg.value >= auc.startPrice, "Below start price");
        require(msg.value > auc.highestBid, "Bid too low");
        require(msg.value >= auc.highestBid + (auc.highestBid * MIN_BID_INCREMENT) / 10000, "Below min increment");

        if (auc.highestBidder != address(0)) {
            (bool refunded, ) = auc.highestBidder.call{value: auc.highestBid}("");
            require(refunded, "Refund failed");
        }

        auc.highestBidder = msg.sender;
        auc.highestBid = msg.value;

        emit BidPlaced(auctionId, msg.sender, msg.value);
    }

    function settleAuction(uint256 auctionId) external {
        Auction storage auc = auctions[auctionId];
        require(auc.active, "Auction not active");
        require(block.timestamp >= auc.endTime, "Auction still active");

        auc.active = false;

        if (auc.highestBidder == address(0)) {
            emit AuctionSettled(auctionId, address(0), 0);
            return;
        }

        if (auc.highestBid < auc.reservePrice) {
            (bool refunded, ) = auc.highestBidder.call{value: auc.highestBid}("");
            require(refunded, "Refund failed");
            emit AuctionSettled(auctionId, address(0), 0);
            return;
        }

        uint256 fee = (auc.highestBid * platformFee) / 10000;
        uint256 sellerProceeds = auc.highestBid - fee;

        IERC721(auc.nftContract).transferFrom(auc.seller, auc.highestBidder, auc.tokenId);

        (bool feeSent, ) = feeRecipient.call{value: fee}("");
        require(feeSent, "Fee transfer failed");

        (bool sellerSent, ) = auc.seller.call{value: sellerProceeds}("");
        require(sellerSent, "Seller transfer failed");

        emit AuctionSettled(auctionId, auc.highestBidder, auc.highestBid);
    }

    function getAuction(uint256 auctionId) external view returns (Auction memory) {
        return auctions[auctionId];
    }
}
