// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow

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
/// @notice Adapter for Chainlink price feeds with normalized 18-decimal output and multi-hop derivation
/// @dev Wraps one or more Chainlink aggregators behind a simple getPrice interface.
///      Supports derived prices via two feeds when no direct feed exists.
contract ChainlinkAdapter {
    address public admin;
    uint256 public constant TARGET_DECIMALS = 18;

    struct FeedConfig {
        AggregatorV3Interface feed;
        uint256 heartbeat; // max seconds between updates
        bool active;
    }

    mapping(address => FeedConfig) public feeds;

    event FeedRegistered(address indexed token, address feed, uint256 heartbeat);
    event FeedDeactivated(address indexed token);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor() {
        admin = msg.sender;
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

    /// @notice Get the validated price from a single feed, normalized to 18 decimals.
    /// @param token The token address whose feed to query.
    /// @return Normalized price in 18-decimal fixed point.
    function getPrice(address token) public view returns (uint256) {
        FeedConfig storage config = feeds[token];
        require(config.active, "Feed not active");

        (
            uint80 roundId,
            int256 answer,
            /* uint256 startedAt */,
            uint256 updatedAt,
            uint80 answeredInRound
        ) = config.feed.latestRoundData();

        // Validate round completeness — answer must be from current round
        require(answeredInRound >= roundId, "Stale round data");
        // Validate staleness against heartbeat
        require(block.timestamp - updatedAt <= config.heartbeat, "Price stale");
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

    /// @notice Derive a price from two feeds when no direct feed exists.
    ///         E.g., TOKEN/ETH = TOKEN/USD ÷ ETH/USD.
    /// @param base The base asset (numerator feed).
    /// @param quote The quote asset (denominator feed).
    /// @return Derived price normalized to 18 decimals.
    function derivedPrice(address base, address quote) external view returns (uint256) {
        // If a direct feed exists for the pair, prefer it
        // Convention: direct feed registered under keccak256(base, quote) or similar
        // For simplicity, check if base itself has a feed that represents base/quote
        // In practice, callers register derived pairs explicitly

        uint256 basePrice = getPrice(base);
        uint256 quotePrice = getPrice(quote);

        require(quotePrice > 0, "Quote price zero");

        // Both prices are already normalized to 18 decimals
        // derived = basePrice / quotePrice, but we need to maintain 18 decimal precision
        // result = (basePrice * 1e18) / quotePrice
        return (basePrice * (10 ** TARGET_DECIMALS)) / quotePrice;
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
