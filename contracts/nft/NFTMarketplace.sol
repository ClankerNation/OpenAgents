// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Contributor: Gaotax2006
// Platform: warpSpeed, opencode CLI
// Runtime: OS=win32 Arch=x64 Home=C:\Users\asus WorkDir=F:\ai-bounty-work\bounty-hunter\openagents Shell=powershell
// Date: 2026-05-17

interface IERC721 {
    function ownerOf(uint256 tokenId) external view returns (address);
    function transferFrom(address from, address to, uint256 tokenId) external;
    function getApproved(uint256 tokenId) external view returns (address);
}

interface IERC2981 {
    function royaltyInfo(uint256 tokenId, uint256 salePrice)
        external view returns (address receiver, uint256 royaltyAmount);
}

contract NFTMarketplace {
    struct Listing {
        address seller;
        address nftContract;
        uint256 tokenId;
        uint256 price;
        bool active;
        uint256 deadline;
        uint256 cancelLockTime;
    }

    struct Auction {
        address seller;
        address nftContract;
        uint256 tokenId;
        uint256 startPrice;
        uint256 reservePrice;
        uint256 duration;
        uint256 endTime;
        address highestBidder;
        uint256 highestBid;
        bool settled;
        bool exists;
    }

    uint256 public constant LISTING_DURATION = 30 days;
    uint256 public constant CANCEL_LOCK_PERIOD = 1 hours;
    uint256 public constant MIN_BID_INCREMENT_BPS = 500;
    uint256 public constant MIN_AUCTION_DURATION = 1 hours;
    uint256 public constant MAX_AUCTION_DURATION = 7 days;

    uint256 public nextListingId;
    uint256 public nextAuctionId;
    uint256 public platformFee;
    address public feeRecipient;

    mapping(uint256 => Listing) public listings;
    mapping(uint256 => Auction) public auctions;

    event Listed(uint256 indexed listingId, address indexed seller, address nftContract, uint256 tokenId, uint256 price);
    event Sold(uint256 indexed listingId, address indexed buyer, uint256 price);
    event Canceled(uint256 indexed listingId);
    event AuctionCreated(uint256 indexed auctionId, address indexed seller, address nftContract, uint256 tokenId, uint256 startPrice, uint256 reservePrice, uint256 duration);
    event BidPlaced(uint256 indexed auctionId, address indexed bidder, uint256 amount);
    event AuctionSettled(uint256 indexed auctionId, address indexed winner, uint256 amount);

    constructor(uint256 _platformFee, address _feeRecipient) {
        require(_feeRecipient != address(0), "Zero fee recipient");
        platformFee = _platformFee;
        feeRecipient = _feeRecipient;
    }

    function listNFT(address nftContract, uint256 tokenId, uint256 price) external returns (uint256) {
        require(price > 0, "Zero price");
        IERC721 nft = IERC721(nftContract);
        require(nft.ownerOf(tokenId) == msg.sender, "Not NFT owner");
        require(nft.getApproved(tokenId) == address(this), "Not approved");

        uint256 listingId = nextListingId++;
        listings[listingId] = Listing({
            seller: msg.sender,
            nftContract: nftContract,
            tokenId: tokenId,
            price: price,
            active: true,
            deadline: block.timestamp + LISTING_DURATION,
            cancelLockTime: block.timestamp + CANCEL_LOCK_PERIOD
        });

        emit Listed(listingId, msg.sender, nftContract, tokenId, price);
        return listingId;
    }

    function buyNFT(uint256 listingId) external payable {
        Listing storage listing = listings[listingId];
        require(listing.active, "Not active");
        require(msg.value == listing.price, "Wrong price");
        require(block.timestamp <= listing.deadline, "Listing expired");

        listing.active = false;

        uint256 fee = (msg.value * platformFee) / 10000;
        uint256 sellerProceeds = msg.value - fee;

        address royaltyRecipient;
        uint256 royaltyAmount;
        try IERC2981(listing.nftContract).royaltyInfo(listing.tokenId, msg.value) returns (address r, uint256 a) {
            royaltyRecipient = r;
            royaltyAmount = a;
        } catch {
            royaltyRecipient = address(0);
            royaltyAmount = 0;
        }

        IERC721(listing.nftContract).transferFrom(listing.seller, msg.sender, listing.tokenId);

        if (royaltyAmount > 0 && royaltyRecipient != address(0)) {
            (bool royaltySent, ) = royaltyRecipient.call{value: royaltyAmount}("");
            if (royaltySent) {
                fee += royaltyAmount / 2;
                sellerProceeds = msg.value - fee - royaltyAmount;
            }
        }

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
        require(block.timestamp >= listing.cancelLockTime, "Cancel locked");

        listing.active = false;
        emit Canceled(listingId);
    }

    function createAuction(address nftContract, uint256 tokenId, uint256 startPrice, uint256 reservePrice, uint256 duration) external returns (uint256) {
        require(startPrice > 0, "Zero start price");
        require(reservePrice >= startPrice, "Reserve below start");
        require(duration >= MIN_AUCTION_DURATION && duration <= MAX_AUCTION_DURATION, "Invalid duration");

        IERC721 nft = IERC721(nftContract);
        require(nft.ownerOf(tokenId) == msg.sender, "Not NFT owner");
        require(nft.getApproved(tokenId) == address(this), "Not approved");

        uint256 auctionId = nextAuctionId++;
        auctions[auctionId] = Auction({
            seller: msg.sender,
            nftContract: nftContract,
            tokenId: tokenId,
            startPrice: startPrice,
            reservePrice: reservePrice,
            duration: duration,
            endTime: block.timestamp + duration,
            highestBidder: address(0),
            highestBid: 0,
            settled: false,
            exists: true
        });

        emit AuctionCreated(auctionId, msg.sender, nftContract, tokenId, startPrice, reservePrice, duration);
        return auctionId;
    }

    function placeBid(uint256 auctionId) external payable {
        Auction storage a = auctions[auctionId];
        require(a.exists, "Auction not found");
        require(block.timestamp < a.endTime, "Auction ended");

        uint256 minBid = a.highestBidder == address(0)
            ? a.startPrice
            : a.highestBid + (a.highestBid * MIN_BID_INCREMENT_BPS) / 10000;
        require(msg.value >= minBid, "Bid too low");

        address previousBidder = a.highestBidder;
        uint256 previousBid = a.highestBid;

        a.highestBidder = msg.sender;
        a.highestBid = msg.value;

        if (previousBidder != address(0)) {
            (bool refunded, ) = previousBidder.call{value: previousBid}("");
            require(refunded, "Refund failed");
        }

        emit BidPlaced(auctionId, msg.sender, msg.value);
    }

    function settleAuction(uint256 auctionId) external {
        Auction storage a = auctions[auctionId];
        require(a.exists, "Auction not found");
        require(!a.settled, "Already settled");
        require(block.timestamp >= a.endTime, "Auction still active");

        a.settled = true;

        if (a.highestBidder == address(0) || a.highestBid < a.reservePrice) {
            emit AuctionSettled(auctionId, address(0), 0);
            return;
        }

        address winner = a.highestBidder;
        uint256 winningBid = a.highestBid;

        IERC721(a.nftContract).transferFrom(a.seller, winner, a.tokenId);

        uint256 fee = (winningBid * platformFee) / 10000;
        uint256 sellerProceeds = winningBid - fee;

        (bool feeSent, ) = feeRecipient.call{value: fee}("");
        require(feeSent, "Fee transfer failed");

        (bool sellerSent, ) = a.seller.call{value: sellerProceeds}("");
        require(sellerSent, "Seller transfer failed");

        emit AuctionSettled(auctionId, winner, winningBid);
    }

    function getListing(uint256 listingId) external view returns (Listing memory) {
        return listings[listingId];
    }

    function getAuction(uint256 auctionId) external view returns (Auction memory) {
        return auctions[auctionId];
    }
}
