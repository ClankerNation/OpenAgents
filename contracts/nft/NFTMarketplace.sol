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

interface IERC2981 {
    function royaltyInfo(uint256 tokenId, uint256 salePrice) external view returns (address receiver, uint256 royaltyAmount);
}

/// @title NFTMarketplace
/// @notice Decentralized marketplace for listing, buying, and canceling NFT sales
/// @dev Supports ERC721 NFTs with ERC-2981 royalty enforcement, listing expiry,
///      time-delayed cancellation to prevent front-running, and zero-price rejection.
contract NFTMarketplace {
    struct Listing {
        address seller;
        address nftContract;
        uint256 tokenId;
        uint256 price;
        uint256 expiresAt;
        uint256 cancelAvailableAt; // timestamp when cancellation becomes available
        bool active;
    }

    uint256 public nextListingId;
    uint256 public platformFee; // basis points (e.g., 250 = 2.5%)
    address public feeRecipient;
    uint256 public constant CANCEL_DELAY = 30 minutes; // time delay before cancel allowed
    uint256 public constant MAX_LISTING_DURATION = 30 days;

    mapping(uint256 => Listing) public listings;

    event Listed(uint256 indexed listingId, address indexed seller, address nftContract, uint256 tokenId, uint256 price, uint256 expiresAt);
    event Sold(uint256 indexed listingId, address indexed buyer, uint256 price, address royaltyReceiver, uint256 royaltyAmount);
    event Canceled(uint256 indexed listingId);

    constructor(uint256 _platformFee, address _feeRecipient) {
        platformFee = _platformFee;
        feeRecipient = _feeRecipient;
    }

    /// @notice List an NFT for sale with price validation and expiry.
    /// @param nftContract The ERC721 contract address.
    /// @param tokenId The token ID to list.
    /// @param price Sale price in wei (must be > 0).
    /// @param durationSeconds How long the listing remains valid (max 30 days).
    /// @return listingId The unique listing identifier.
    function listNFT(
        address nftContract,
        uint256 tokenId,
        uint256 price,
        uint256 durationSeconds
    ) external returns (uint256) {
        require(price > 0, "Price must be greater than zero");
        require(durationSeconds > 0 && durationSeconds <= MAX_LISTING_DURATION, "Invalid duration");

        IERC721 nft = IERC721(nftContract);
        require(nft.ownerOf(tokenId) == msg.sender, "Not NFT owner");
        require(nft.getApproved(tokenId) == address(this), "Marketplace not approved");

        uint256 listingId = nextListingId++;
        uint256 expiresAt = block.timestamp + durationSeconds;

        listings[listingId] = Listing({
            seller: msg.sender,
            nftContract: nftContract,
            tokenId: tokenId,
            price: price,
            expiresAt: expiresAt,
            cancelAvailableAt: block.timestamp + CANCEL_DELAY,
            active: true
        });

        emit Listed(listingId, msg.sender, nftContract, tokenId, price, expiresAt);
        return listingId;
    }

    /// @notice Buy a listed NFT with automatic royalty distribution via ERC-2981.
    /// @param listingId The listing to purchase.
    function buyNFT(uint256 listingId) external payable {
        Listing storage listing = listings[listingId];
        require(listing.active, "Not active");
        require(block.timestamp <= listing.expiresAt, "Listing expired");
        require(msg.value == listing.price, "Wrong price");

        listing.active = false;

        // Calculate platform fee
        uint256 fee = (msg.value * platformFee) / 10000;
        uint256 remaining = msg.value - fee;

        // Check for ERC-2981 royalties
        uint256 royaltyAmount = 0;
        address royaltyReceiver = address(0);

        try IERC2981(listing.nftContract).royaltyInfo(listing.tokenId, msg.value) returns (address receiver, uint256 amount) {
            if (receiver != address(0) && amount > 0 && amount <= remaining) {
                royaltyReceiver = receiver;
                royaltyAmount = amount;
                remaining -= royaltyAmount;
            }
        } catch {
            // Contract doesn't support ERC-2981 — no royalties
        }

        // Transfer NFT to buyer
        IERC721(listing.nftContract).transferFrom(listing.seller, msg.sender, listing.tokenId);

        // Pay platform fee
        (bool feeSent, ) = feeRecipient.call{value: fee}("");
        require(feeSent, "Fee transfer failed");

        // Pay royalties if applicable
        if (royaltyAmount > 0) {
            (bool royaltySent, ) = royaltyReceiver.call{value: royaltyAmount}("");
            require(royaltySent, "Royalty transfer failed");
        }

        // Pay seller proceeds
        (bool sellerSent, ) = listing.seller.call{value: remaining}("");
        require(sellerSent, "Seller transfer failed");

        emit Sold(listingId, msg.sender, msg.value, royaltyReceiver, royaltyAmount);
    }

    /// @notice Cancel a listing after the mandatory time delay to prevent front-running.
    /// @param listingId The listing to cancel.
    function cancelListing(uint256 listingId) external {
        Listing storage listing = listings[listingId];
        require(listing.active, "Not active");
        require(listing.seller == msg.sender, "Not seller");
        require(block.timestamp >= listing.cancelAvailableAt, "Cancel delay not elapsed");

        listing.active = false;
        emit Canceled(listingId);
    }

    function getListing(uint256 listingId) external view returns (Listing memory) {
        return listings[listingId];
    }
}
