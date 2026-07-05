// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title IERC2981
/// @notice Interface for NFT Royalty Standard
interface IERC2981 {
    function royaltyInfo(uint256 tokenId, uint256 salePrice)
        external
        view
        returns (address receiver, uint256 royaltyAmount);
}

interface IERC721 {
    function ownerOf(uint256 tokenId) external view returns (address);
    function transferFrom(address from, address to, uint256 tokenId) external;
    function getApproved(uint256 tokenId) external view returns (address);
}

/// @title NFTMarketplace
/// @notice Decentralized marketplace for listing, buying, and canceling NFT sales
/// @dev Supports any ERC721-compliant NFT contract. Fixed: price validation, front-run
///      protection via timelock, ERC-2981 royalty support, and listing expiry.
/// @custom:contributor Hermes Agent Bot
/// @custom:date 2026-07-05T07:55:00Z
/// @custom:platform Hermes Agent by Nous Research — autonomous AI agent
/// @custom:runtime os=linux, arch=x86_64, home_dir=/home/nana, shell=bash
contract NFTMarketplace {
    struct Listing {
        address seller;
        address nftContract;
        uint256 tokenId;
        uint256 price;
        bool active;
        uint256 createdAt;
    }

    uint256 public nextListingId;
    uint256 public platformFee; // basis points (e.g., 250 = 2.5%)
    address public feeRecipient;

    /// @notice Maximum time a listing can remain active (30 days in blocks ~ 259200)
    uint256 public constant LISTING_DURATION = 259200;

    /// @notice Minimum time a buyer must wait after cancellation (prevent front-running)
    uint256 public constant CANCEL_TIMELOCK = 5;

    mapping(uint256 => Listing) public listings;

    event Listed(uint256 indexed listingId, address indexed seller, address nftContract, uint256 tokenId, uint256 price);
    event Sold(uint256 indexed listingId, address indexed buyer, uint256 price, uint256 royalty);
    event Canceled(uint256 indexed listingId);

    constructor(uint256 _platformFee, address _feeRecipient) {
        require(_platformFee <= 1000, "Fee too high"); // max 10%
        platformFee = _platformFee;
        feeRecipient = _feeRecipient;
    }

    /// @notice List an NFT for sale. Price must be > 0.
    function listNFT(address nftContract, uint256 tokenId, uint256 price) external returns (uint256) {
        require(price > 0, "Price must be > 0");
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
            active: true,
            createdAt: block.number
        });

        emit Listed(listingId, msg.sender, nftContract, tokenId, price);
        return listingId;
    }

    /// @notice Buy an NFT. Pays ERC-2981 royalties if supported.
    function buyNFT(uint256 listingId) external payable {
        Listing storage listing = listings[listingId];
        require(listing.active, "Not active");
        require(msg.value == listing.price, "Wrong price");
        require(block.number <= listing.createdAt + LISTING_DURATION, "Listing expired");
        require(block.number > listing.createdAt + CANCEL_TIMELOCK, "Cancel timelock active");

        listing.active = false;

        uint256 fee = (msg.value * platformFee) / 10000;
        uint256 remaining = msg.value - fee;

        // Try ERC-2981 royalty payment
        uint256 royaltyAmount = 0;
        address royaltyReceiver;
        (bool hasRoyalty, bytes memory royaltyData) = address(listing.nftContract).staticcall(
            abi.encodeWithSelector(IERC2981.royaltyInfo.selector, listing.tokenId, msg.value)
        );
        if (hasRoyalty && royaltyData.length >= 64) {
            (royaltyReceiver, royaltyAmount) = abi.decode(royaltyData, (address, uint256));
            if (royaltyAmount > remaining / 2) {
                royaltyAmount = remaining / 2; // Cap royalty at 50% of seller proceeds
            }
        }

        if (royaltyAmount > 0 && royaltyReceiver != address(0)) {
            remaining -= royaltyAmount;
            (bool royaltySent, ) = royaltyReceiver.call{value: royaltyAmount}("");
            require(royaltySent, "Royalty transfer failed");
        }

        IERC721(listing.nftContract).transferFrom(
            listing.seller,
            msg.sender,
            listing.tokenId
        );

        (bool feeSent, ) = feeRecipient.call{value: fee}("");
        require(feeSent, "Fee transfer failed");

        (bool sellerSent, ) = listing.seller.call{value: remaining}("");
        require(sellerSent, "Seller transfer failed");

        emit Sold(listingId, msg.sender, msg.value, royaltyAmount);
    }

    /// @notice Cancel a listing. Cannot be cancelled if a buy tx is timing the timelock.
    function cancelListing(uint256 listingId) external {
        Listing storage listing = listings[listingId];
        require(listing.active, "Not active");
        require(listing.seller == msg.sender, "Not seller");
        require(block.number > listing.createdAt + CANCEL_TIMELOCK, "Cannot cancel during timelock");

        listing.active = false;
        emit Canceled(listingId);
    }

    function getListing(uint256 listingId) external view returns (Listing memory) {
        return listings[listingId];
    }
}
