// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * @fix-author Claude Fable 5 (Autonomous Agent)
 * @date 2026-08-20T13:10:00Z
 * @platform [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 * @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 */

interface IERC721 {
    function ownerOf(uint256 tokenId) external view returns (address);
    function transferFrom(address from, address to, uint256 tokenId) external;
    function getApproved(uint256 tokenId) external view returns (address);
}

interface IERC2981 {
    function royaltyInfo(uint256 tokenId, uint256 salePrice) external view returns (address receiver, uint256 royaltyAmount);
}

/// @title NFTMarketplace
/// @notice Decentralized marketplace for listing, buying, and canceling NFT sales
/// @dev Supports any ERC721-compliant NFT contract and ERC-2981 royalties
contract NFTMarketplace {
    struct Listing {
        address seller;
        address nftContract;
        uint256 tokenId;
        uint256 price;
        uint256 expiry;
        uint256 cancelInitiatedAt;
        bool active;
    }

    uint256 public nextListingId;
    uint256 public platformFee; // basis points (e.g., 250 = 2.5%)
    address public feeRecipient;
    uint256 public constant CANCEL_DELAY = 1 hours;

    mapping(uint256 => Listing) public listings;

    event Listed(uint256 indexed listingId, address indexed seller, address nftContract, uint256 tokenId, uint256 price, uint256 expiry);
    event Sold(uint256 indexed listingId, address indexed buyer, uint256 price);
    event CancelRequested(uint256 indexed listingId, uint256 executableAt);
    event Canceled(uint256 indexed listingId);

    constructor(uint256 _platformFee, address _feeRecipient) {
        platformFee = _platformFee;
        feeRecipient = _feeRecipient;
    }

    function listNFT(address nftContract, uint256 tokenId, uint256 price, uint256 expiry) external returns (uint256) {
        IERC721 nft = IERC721(nftContract);
        require(nft.ownerOf(tokenId) == msg.sender, "Not NFT owner");
        require(
            nft.getApproved(tokenId) == address(this),
            "Marketplace not approved"
        );
        require(price > 0, "Price must be > 0");
        require(expiry > block.timestamp, "Invalid expiry");

        uint256 listingId = nextListingId++;
        listings[listingId] = Listing({
            seller: msg.sender,
            nftContract: nftContract,
            tokenId: tokenId,
            price: price,
            expiry: expiry,
            cancelInitiatedAt: 0,
            active: true
        });

        emit Listed(listingId, msg.sender, nftContract, tokenId, price, expiry);
        return listingId;
    }

    function buyNFT(uint256 listingId) external payable {
        Listing storage listing = listings[listingId];
        require(listing.active, "Not active");
        require(block.timestamp <= listing.expiry, "Listing expired");
        require(msg.value == listing.price, "Wrong price");
        require(listing.cancelInitiatedAt == 0, "Cancel in progress");

        listing.active = false;

        uint256 salePrice = msg.value;
        uint256 royaltyAmount = 0;
        address royaltyReceiver = address(0);

        // Try to get ERC-2981 royalty info
        try IERC2981(listing.nftContract).royaltyInfo(listing.tokenId, salePrice) returns (address receiver, uint256 amount) {
            if (receiver != address(0) && amount > 0) {
                royaltyReceiver = receiver;
                royaltyAmount = amount;
                require(salePrice >= royaltyAmount + ((salePrice * platformFee) / 10000), "Royalty + fee exceeds price");
            }
        } catch {}

        uint256 fee = (salePrice * platformFee) / 10000;
        uint256 sellerProceeds = salePrice - fee - royaltyAmount;

        IERC721(listing.nftContract).transferFrom(
            listing.seller,
            msg.sender,
            listing.tokenId
        );

        if (royaltyAmount > 0) {
            (bool royaltySent, ) = royaltyReceiver.call{value: royaltyAmount}("");
            require(royaltySent, "Royalty transfer failed");
        }

        (bool feeSent, ) = feeRecipient.call{value: fee}("");
        require(feeSent, "Fee transfer failed");

        (bool sellerSent, ) = listing.seller.call{value: sellerProceeds}("");
        require(sellerSent, "Seller transfer failed");

        emit Sold(listingId, msg.sender, salePrice);
    }

    function requestCancel(uint256 listingId) external {
        Listing storage listing = listings[listingId];
        require(listing.active, "Not active");
        require(listing.seller == msg.sender, "Not seller");
        require(listing.cancelInitiatedAt == 0, "Cancel already requested");

        listing.cancelInitiatedAt = block.timestamp;
        emit CancelRequested(listingId, block.timestamp + CANCEL_DELAY);
    }

    function executeCancel(uint256 listingId) external {
        Listing storage listing = listings[listingId];
        require(listing.active, "Not active");
        require(listing.seller == msg.sender, "Not seller");
        require(listing.cancelInitiatedAt > 0, "Cancel not requested");
        require(block.timestamp >= listing.cancelInitiatedAt + CANCEL_DELAY, "Delay not passed");

        listing.active = false;
        emit Canceled(listingId);
    }

    function getListing(uint256 listingId) external view returns (Listing memory) {
        return listings[listingId];
    }
}
