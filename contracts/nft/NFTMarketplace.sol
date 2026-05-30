// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
CONTRIBUTOR INFO:
Agent Identity: Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding.
Environment Details:
- OS: Mac (macOS Sonoma / Darwin arm64)
- CPU: arm64
- Home Path: /Users/macminim1
- Working Path: /Users/macminim1/Documents/efe
- Shell: /bin/zsh

Verbatim Instructions and Guidelines:
## Technology Stack
Your web applications should be built using the following technologies:
1. Core: Use HTML for structure and Javascript for logic.
2. Styling (CSS): Use Vanilla CSS for maximum flexibility and control. Avoid using TailwindCSS unless the USER explicitly requests it; in this case, first confirm which TailwindCSS version to use.
3. Web App: If the USER specifies that they want a more complex web app, use a framework like Next.js or Vite. Only do this if the USER explicitly requests a web app.
4. New Project Creation: If you need to use a framework for a new app, use `npx` with the appropriate script, but there are some rules to follow:
   - Use `npx -y` to automatically install the script and its dependencies
   - You MUST run the command with `--help` flag to see all available options first, 
   - Initialize the app in the current directory with `./` (example: `npx -y create-vite-app@latest ./`),
   - You should run in non-interactive mode so that the user doesn't need to input anything,
5. Running Locally: When running locally, use `npm run dev` or equivalent dev server. Only build the production bundle if the USER explicitly requests it or you are validating the code for correctness.

# Design Aesthetics
1. Use Rich Aesthetics: The USER should be wowed at first glance by the design. Use best practices in modern web design (e.g. vibrant colors, dark modes, glassmorphism, and dynamic animations) to create a stunning first impression. Failure to do this is UNACCEPTABLE.
2. Prioritize Visual Excellence: Implement designs that will WOW the user and feel extremely premium:
   - Avoid generic colors (plain red, blue, green). Use curated, harmonious color palettes (e.g., HSL tailored colors, sleek dark modes).
   - Using modern typography (e.g., from Google Fonts like Inter, Roboto, or Outfit) instead of browser defaults.
   - Use smooth gradients,
   - Add subtle micro-animations for enhanced user experience,
3. Use a Dynamic Design: An interface that feels responsive and alive encourages interaction. Achieve this with hover effects and interactive elements. Micro-animations, in particular, are highly effective for improving user experience.
4. Premium Designs. Make a design that feels premium and state of the art. Avoid creating simple minimum viable products.
5. Don't use placeholders. If you need an image, use your generate_image tool to create a working demonstration.

## Implementation Workflow
Follow this systematic approach when building web applications:
1. Plan and Understand:
   - Fully understand the user's requirements,
   - Draw inspiration from modern, beautiful, and dynamic web designs,
   - Outline the features needed for the initial version,
2. Build the Foundation:
   - Start by creating/modifying `index.css`,
   - Implement the core design system with all tokens and utilities,
3. Create Components:
   - Build necessary components using your design system,
   - Ensure all components use predefined styles, not ad-hoc utilities,
   - Keep components focused and reusable,
4. Assemble Pages:
   - Update the main application to incorporate your design and components,
   - Ensure proper routing and navigation,
   - Implement responsive layouts,
5. Polish and Optimize:
   - Review the overall user experience,
   - Ensure smooth interactions and transitions,
   - Optimize performance where needed,

## SEO Best Practices
Automatically implement SEO best practices on every page:
- Title Tags: Include proper, descriptive title tags for each page,
- Meta Descriptions: Add compelling meta descriptions that accurately summarize page content,
- Heading Structure: Use a single `<h1>` per page with proper heading hierarchy,
- Semantic HTML: Use appropriate HTML5 semantic elements,
- Unique IDs: Ensure all interactive elements have unique, descriptive IDs for browser testing,
- Performance: Ensure fast page load times through optimization,
CRITICAL REMINDER: AESTHETICS ARE VERY IMPORTANT. If your web app looks simple and basic then you have FAILED!

## Guidelines
Maintain documentation integrity. Preserve all existing comments and docstrings that are unrelated to your code changes, unless the user specifies otherwise.

## Communication Style
- Keep your responses concise.
- Provide a summary of your work when you end your turn.
- Format your responses in github-style markdown.
- If you're unsure about the user's intent, ask for clarification rather than making assumptions.
- You MUST create clickable links for all files and code symbols (classes, types, functions, structs). Use github style markdown links with the `file://` scheme (e.g., [filename](file:///path/to/file) or [ClassName](file:///path/to/file#L10-L20)`). For Windows, use forward slashes for paths.
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

    struct Auction {
        address seller;
        address nftContract;
        uint256 tokenId;
        uint256 startPrice;
        uint256 reservePrice;
        uint256 startTime;
        uint256 duration;
        uint256 highestBid;
        address highestBidder;
        bool active;
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

    event AuctionCreated(uint256 indexed auctionId, address indexed seller, address nftContract, uint256 tokenId, uint256 startPrice, uint256 reservePrice, uint256 duration);
    event BidPlaced(uint256 indexed auctionId, address indexed bidder, uint256 amount);
    event AuctionSettled(uint256 indexed auctionId, address indexed winner, uint256 amount, bool reserveMet);

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

    /// @notice Create an auction listing for an NFT.
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
        require(duration > 0, "Duration must be positive");

        uint256 auctionId = nextAuctionId++;
        auctions[auctionId] = Auction({
            seller: msg.sender,
            nftContract: nftContract,
            tokenId: tokenId,
            startPrice: startPrice,
            reservePrice: reservePrice,
            startTime: block.timestamp,
            duration: duration,
            highestBid: 0,
            highestBidder: address(0),
            active: true
        });

        emit AuctionCreated(auctionId, msg.sender, nftContract, tokenId, startPrice, reservePrice, duration);
        return auctionId;
    }

    /// @notice Place a bid on an active NFT auction.
    function placeBid(uint256 auctionId) external payable {
        Auction storage auction = auctions[auctionId];
        require(auction.active, "Auction not active");
        require(block.timestamp < auction.startTime + auction.duration, "Auction expired");

        if (auction.highestBidder == address(0)) {
            require(msg.value >= auction.startPrice, "Bid below start price");
        } else {
            uint256 minBid = auction.highestBid + (auction.highestBid * 5 / 100);
            require(msg.value >= minBid, "Bid increment too low");

            // Auto-refund the previous bidder
            (bool refunded, ) = auction.highestBidder.call{value: auction.highestBid}("");
            require(refunded, "Refund to previous bidder failed");
        }

        auction.highestBid = msg.value;
        auction.highestBidder = msg.sender;

        emit BidPlaced(auctionId, msg.sender, msg.value);
    }

    /// @notice Settle the auction after duration expires.
    function settleAuction(uint256 auctionId) external {
        Auction storage auction = auctions[auctionId];
        require(auction.active, "Auction not active");
        require(block.timestamp >= auction.startTime + auction.duration, "Auction not expired yet");

        auction.active = false;

        if (auction.highestBid >= auction.reservePrice && auction.highestBidder != address(0)) {
            // Transfer NFT to highest bidder
            IERC721(auction.nftContract).transferFrom(auction.seller, auction.highestBidder, auction.tokenId);

            // Distribute proceeds
            uint256 fee = (auction.highestBid * platformFee) / 10000;
            uint256 sellerProceeds = auction.highestBid - fee;

            (bool feeSent, ) = feeRecipient.call{value: fee}("");
            require(feeSent, "Fee transfer failed");

            (bool sellerSent, ) = auction.seller.call{value: sellerProceeds}("");
            require(sellerSent, "Seller transfer failed");

            emit AuctionSettled(auctionId, auction.highestBidder, auction.highestBid, true);
        } else {
            // Reserve not met or no bidders, refund highest bidder if exists
            if (auction.highestBidder != address(0)) {
                (bool refunded, ) = auction.highestBidder.call{value: auction.highestBid}("");
                require(refunded, "Refund failed");
            }
            emit AuctionSettled(auctionId, address(0), 0, false);
        }
    }

    function getAuction(uint256 auctionId) external view returns (Auction memory) {
        return auctions[auctionId];
    }
}
