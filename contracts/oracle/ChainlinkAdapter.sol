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
/// @notice Adapter for Chainlink price feeds with normalized 18-decimal output
/// @dev Wraps one or more Chainlink aggregators behind a simple getPrice interface.
///      Supports multi-hop price derivation for pairs without direct feeds.
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

    /// @notice Get validated price from a single feed with full safety checks.
    /// @param token The token address key for the feed config.
    /// @return price Normalized to 18 decimals.
    function getPrice(address token) external view returns (uint256) {
        return _getValidatedPrice(token);
    }

    /// @notice Derive price for base/quote pair using two feeds when no direct feed exists.
    /// @dev Calculates: derivedPrice = basePrice / quotePrice, normalized to 18 decimals.
    ///      Example: TOKEN/ETH via TOKEN/USD and ETH/USD feeds.
    /// @param base The base asset token address (must have registered feed).
    /// @param quote The quote asset token address (must have registered feed).
    /// @return price The derived price normalized to 18 decimals.
    function derivedPrice(address base, address quote) external view returns (uint256) {
        // If a direct feed exists for the base/quote pair, prefer it
        // (caller should check getPrice first, but we handle gracefully)
        
        uint256 basePrice = _getValidatedPrice(base);
        uint256 quotePrice = _getValidatedPrice(quote);

        require(quotePrice > 0, "Quote price is zero");

        // Both prices are already normalized to 18 decimals by _getValidatedPrice
        // derivedPrice = basePrice * 1e18 / quotePrice to maintain 18-decimal precision
        return (basePrice * 1e18) / quotePrice;
    }

    /// @notice Internal function to get a validated, staleness-checked, normalized price.
    /// @param token The token address key for the feed config.
    /// @return price Normalized to 18 decimals.
    function _getValidatedPrice(address token) internal view returns (uint256) {
        FeedConfig storage config = feeds[token];
        require(config.active, "Feed not active");

        (
            uint80 roundId,
            int256 answer,
            /* uint256 startedAt */,
            uint256 updatedAt,
            uint80 answeredInRound
        ) = config.feed.latestRoundData();

        // FIX: Validate round completeness — answer must be from current round
        require(answeredInRound >= roundId, "Stale round data");

        // FIX: Reject negative prices — casting negative int256 to uint256 produces huge incorrect values
        require(answer > 0, "Invalid negative price");

        // FIX: Staleness check against configured heartbeat
        require(block.timestamp - updatedAt <= config.heartbeat, "Price stale");

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

    function getFeedInfo(address token) external view returns (
        address feedAddress,
        uint256 heartbeat,
        bool active
    ) {
        FeedConfig storage config = feeds[token];
        return (address(config.feed), config.heartbeat, config.active);
    }
}
