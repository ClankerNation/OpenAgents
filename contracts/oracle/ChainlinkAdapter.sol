// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface AggregatorV3Interface {
    function latestRoundData() external view returns (
        uint80 roundId,
        int256 answer,
        uint256 startedAt,
        uint256 updatedAt,
        uint80 answeredInRound
    );
    function decimals() external view returns (uint8);
}

/// @title ChainlinkAdapter
/// @notice Adapter for Chainlink price feeds with normalized 18-decimal output
/// @dev Supports single-hop and multi-hop price feeds through a base currency (ETH/USD)
contract ChainlinkAdapter {
    address public admin;
    uint256 public constant TARGET_DECIMALS = 18;
    address public immutable baseCurrency;

    struct FeedConfig {
        AggregatorV3Interface feed;
        uint256 heartbeat; // max seconds between updates
        bool active;
    }

    mapping(address => FeedConfig) public feeds;

    event FeedRegistered(address indexed token, address feed, uint256 heartbeat);
    event FeedDeactivated(address indexed token);
    event MultiHopPrice(address indexed srcToken, address indexed dstToken, uint256 price, uint256[] feedPath);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor() {
        admin = msg.sender;
        baseCurrency = 0xDe3E3Ad8574bb6C82bcDa53C93DFDCDb90C33b28; // WETH on mainnet
    }

    function registerFeed(
        address token,
        address feed,
        uint256 heartbeat
    ) external onlyAdmin {
        require(feed != address(0), "Invalid feed");
        require(heartbeat > 0, "Invalid heartbeat");

        feeds[token] = FeedConfig({
            feed: AggregatorV3Interface(feed),
            heartbeat: heartbeat,
            active: true
        });

        emit FeedRegistered(token, feed, heartbeat);
    }

    function deactivateFeed(address token) external onlyAdmin {
        feeds[token].active = false;
        emit FeedDeactivated(token);
    }

    // FIXED: Added roundId completeness check, staleness check, and negative price rejection
    function getPrice(address token) external view returns (uint256) {
        FeedConfig storage config = feeds[token];
        require(config.active, "Feed not active");

        (
            uint80 roundId,
            int256 answer,
            /* uint256 startedAt */,
            uint256 updatedAt,
            uint80 answeredInRound
        ) = config.feed.latestRoundData();

        // Check roundId completeness: answeredInRound must equal roundId
        require(answeredInRound == roundId, "Answer from previous round");

        // Check staleness: updatedAt must be within heartbeat
        require(updatedAt >= block.timestamp - config.heartbeat, "Stale price");

        // Reject negative prices
        require(answer > 0, "Negative price");

        uint256 price = uint256(answer);

        // Normalize to 18 decimals
        uint8 feedDecimals = config.feed.decimals();
        if (feedDecimals < TARGET_DECIMALS) {
            price = price * (10 ** (TARGET_DECIMALS - feedDecimals));
        } else if (feedDecimals > TARGET_DECIMALS) {
            price = price / (10 ** (feedDecimals - TARGET_DECIMALS));
        }

        return price;
    }

    /**
     * @notice Get price for a token pair using multi-hop via base currency
     * @param srcToken Source token address
     * @param dstToken Destination token address
     * @return price Normalized 18-decimal price of srcToken in dstToken terms
     * @return feedPath Array of aggregator addresses used in the route
     *
     * Example: ETH/USDC (single hop if both quoted in same base)
     *          BTC/DAI (multi-hop: BTC->ETH, ETH->DAI)
     */
    function getMultiHopPrice(
        address srcToken,
        address dstToken
    ) external view returns (uint256 price, address[] memory feedPath) {
        require(srcToken != dstToken, "Same token");

        // Determine route: src -> base -> dst
        // Step 1: srcToken -> baseCurrency
        address srcFeedAddr = address(feeds[srcToken].feed);
        require(srcFeedAddr != address(0), "Src feed not registered");
        require(feeds[srcToken].active, "Src feed not active");

        // Step 2: baseCurrency -> dstToken (reverse: dstToken -> baseCurrency)
        address dstFeedAddr = address(feeds[dstToken].feed);
        require(dstFeedAddr != address(0), "Dst feed not registered");
        require(feeds[dstToken].active, "Dst feed not active");

        feedPath = new address[](2);
        feedPath[0] = srcFeedAddr;
        feedPath[1] = dstFeedAddr;

        // Get srcToken price in base currency terms
        uint256 srcPrice = _getValidatedPrice(srcToken);
        // Get dstToken price in base currency terms
        uint256 dstPrice = _getValidatedPrice(dstToken);

        // Cross-rate: srcPrice / dstPrice (both normalized to 18 decimals)
        price = (srcPrice * (10 ** TARGET_DECIMALS)) / dstPrice;

        emit MultiHopPrice(srcToken, dstToken, price, feedPath);
    }

    /**
     * @notice Get price along a custom multi-hop path
     * @param path Array of token addresses forming the route (e.g., [TOKEN_A, BASE, TOKEN_B])
     * @return price Normalized 18-decimal price
     * @return actualFeeds Array of aggregator addresses actually used
     */
    function getCustomMultiHopPrice(
        address[] calldata path
    ) external view returns (uint256 price, address[] memory actualFeeds) {
        require(path.length >= 3, "Path too short");
        require(path.length % 2 != 0, "Odd hops");

        actualFeeds = new address[](path.length - 1);
        uint256[] memory hopPrices = new uint256[](path.length - 1);

        for (uint256 i = 0; i < path.length - 1; i++) {
            address feedAddr = address(feeds[path[i]].feed);
            require(feedAddr != address(0), "Feed not registered");
            require(feeds[path[i]].active, "Feed not active");
            actualFeeds[i] = feedAddr;
            hopPrices[i] = _getValidatedPrice(path[i]);
        }

        // Multiply/divide along the path
        price = hopPrices[0];
        for (uint256 i = 1; i < hopPrices.length; i++) {
            price = (price * hopPrices[i]) / (10 ** TARGET_DECIMALS);
        }

        emit MultiHopPrice(path[0], path[path.length - 1], price, actualFeeds);
    }

    /**
     * @notice Internal validated price getter (normalizes to 18 decimals)
     */
    function _getValidatedPrice(address token) internal view returns (uint256) {
        FeedConfig storage config = feeds[token];

        (
            uint80 roundId,
            int256 answer,
            /* uint256 startedAt */,
            uint256 updatedAt,
            uint80 answeredInRound
        ) = config.feed.latestRoundData();

        require(answeredInRound == roundId, "Answer from previous round");
        require(updatedAt >= block.timestamp - config.heartbeat, "Stale price");
        require(answer > 0, "Negative price");

        uint256 p = uint256(answer);
        uint8 feedDecimals = config.feed.decimals();
        if (feedDecimals < TARGET_DECIMALS) {
            p = p * (10 ** (TARGET_DECIMALS - feedDecimals));
        } else if (feedDecimals > TARGET_DECIMALS) {
            p = p / (10 ** (feedDecimals - TARGET_DECIMALS));
        }
        return p;
    }

    function getFeedInfo(address token) external view returns (
        address feedAddress,
        uint256 heartbeat,
        bool active
    ) {
        FeedConfig storage config = feeds[token];
        return (address(config.feed), config.heartbeat, config.active);
    }
}
