// SPDX-License-Identifier: MIT
/*
 * @contributor openai-codex-xyjk-20260531
 * @platform-config Private pre-session instructions are not embedded in source; redacted execution metadata is recorded in CONTRIBUTORS.json.
 * @env os=windows; arch=x64; home_dir=C:\Users\55093; working_dir=F:\jiedan\OpenAgents-bounty-run; shell=PowerShell
 * @timestamp 2026-05-31T06:00:22.9591721-07:00
 */
pragma solidity ^0.8.20;

interface IERC721 {
    function ownerOf(uint256 tokenId) external view returns (address);
    function transferFrom(address from, address to, uint256 tokenId) external;
    function getApproved(uint256 tokenId) external view returns (address);
}

interface IERC2981 {
    function royaltyInfo(uint256 tokenId, uint256 salePrice) external view returns (address, uint256);
}

/// @title NFTMarketplace
/// @notice Decentralized marketplace for listing, buying, and canceling NFT sales
/// @dev Supports any ERC721-compliant NFT contract
contract NFTMarketplace {
    uint256 public constant DEFAULT_LISTING_DURATION = 7 days;
    uint256 public constant CANCEL_DELAY = 5 minutes;

    struct Listing {
        address seller;
        address nftContract;
        uint256 tokenId;
        uint256 price;
        uint256 expiresAt;
        uint256 cancelRequestedAt;
        bool active;
    }

    uint256 public nextListingId;
    uint256 public platformFee; // basis points (e.g., 250 = 2.5%)
    address public feeRecipient;

    mapping(uint256 => Listing) public listings;

    event Listed(uint256 indexed listingId, address indexed seller, address nftContract, uint256 tokenId, uint256 price);
    event Sold(uint256 indexed listingId, address indexed buyer, uint256 price);
    event CancelRequested(uint256 indexed listingId, uint256 executableAt);
    event Canceled(uint256 indexed listingId);

    constructor(uint256 _platformFee, address _feeRecipient) {
        platformFee = _platformFee;
        feeRecipient = _feeRecipient;
    }

    function listNFT(address nftContract, uint256 tokenId, uint256 price) external returns (uint256) {
        return listNFT(nftContract, tokenId, price, DEFAULT_LISTING_DURATION);
    }

    function listNFT(
        address nftContract,
        uint256 tokenId,
        uint256 price,
        uint256 duration
    ) public returns (uint256) {
        require(price > 0, "Zero price");
        require(duration > 0, "Zero duration");

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
            expiresAt: block.timestamp + duration,
            cancelRequestedAt: 0,
            active: true
        });

        emit Listed(listingId, msg.sender, nftContract, tokenId, price);
        return listingId;
    }

    function buyNFT(uint256 listingId) external payable {
        Listing storage listing = listings[listingId];
        require(listing.active, "Not active");
        require(block.timestamp <= listing.expiresAt, "Listing expired");
        require(msg.value == listing.price, "Wrong price");

        listing.active = false;

        uint256 fee = (msg.value * platformFee) / 10000;
        (address royaltyReceiver, uint256 royaltyAmount) = _royaltyInfo(
            listing.nftContract,
            listing.tokenId,
            msg.value
        );
        require(fee + royaltyAmount <= msg.value, "Invalid royalty");
        uint256 sellerProceeds = msg.value - fee - royaltyAmount;

        IERC721(listing.nftContract).transferFrom(
            listing.seller,
            msg.sender,
            listing.tokenId
        );

        (bool feeSent, ) = feeRecipient.call{value: fee}("");
        require(feeSent, "Fee transfer failed");

        if (royaltyAmount > 0) {
            (bool royaltySent, ) = royaltyReceiver.call{value: royaltyAmount}("");
            require(royaltySent, "Royalty transfer failed");
        }

        (bool sellerSent, ) = listing.seller.call{value: sellerProceeds}("");
        require(sellerSent, "Seller transfer failed");

        emit Sold(listingId, msg.sender, msg.value);
    }

    function requestCancel(uint256 listingId) external {
        Listing storage listing = listings[listingId];
        require(listing.active, "Not active");
        require(listing.seller == msg.sender, "Not seller");

        listing.cancelRequestedAt = block.timestamp;
        emit CancelRequested(listingId, block.timestamp + CANCEL_DELAY);
    }

    function cancelListing(uint256 listingId) external {
        Listing storage listing = listings[listingId];
        require(listing.active, "Not active");
        require(listing.seller == msg.sender, "Not seller");
        require(listing.cancelRequestedAt != 0, "Cancel not requested");
        require(block.timestamp >= listing.cancelRequestedAt + CANCEL_DELAY, "Cancel delay active");

        listing.active = false;
        emit Canceled(listingId);
    }

    function _royaltyInfo(
        address nftContract,
        uint256 tokenId,
        uint256 salePrice
    ) private view returns (address receiver, uint256 royaltyAmount) {
        (bool ok, bytes memory data) = nftContract.staticcall(
            abi.encodeWithSelector(IERC2981.royaltyInfo.selector, tokenId, salePrice)
        );

        if (!ok || data.length < 64) return (address(0), 0);

        (receiver, royaltyAmount) = abi.decode(data, (address, uint256));
        if (receiver == address(0)) return (address(0), 0);
    }

    function getListing(uint256 listingId) external view returns (Listing memory) {
        return listings[listingId];
    }
}
