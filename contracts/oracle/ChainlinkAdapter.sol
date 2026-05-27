// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// * Contributor: Karry2019web
// * Timestamp: 2026-05-27T08:10:00Z
// * Agent: Hermes Agent (deepseek-chat) — autonomous AI bounty hunter (cron job)
// * Startup: "You are the automated bounty grabbing bot..."
// * Environment: os=Windows_10|arch=amd64|home=C:\Users\Administrator|workdir=C:\Users\Administrator\AppData\Local\hermes\hermes-agent|shell=bash(git-bash)
// * Payment: USDC (Base) — wallet address provided on request

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
///      Supports both direct feeds and derived multi-hop prices via two feeds.
contract ChainlinkAdapter {
    address public admin;
    uint256 public constant TARGET_DECIMALS = 18;

    struct FeedConfig {
        AggregatorV3Interface feed;
        uint256 heartbeat;
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

    /// @notice Get the direct price for a token via its registered feed
    /// @param token Address of the token to query
    /// @return price Normalized price in 18 decimals
    function getPrice(address token) external view returns (uint256 price) {
        return _getPrice(token);
    }

    /// @notice Get a derived price for a pair without a direct feed
    /// @dev Computes price(base) / price(quote) using two registered feeds.
    ///      Both feeds are validated for staleness and completeness.
    ///      Example: TOKEN/ETH = TOKEN/USD / ETH/USD
    /// @param base Base token address
    /// @param quote Quote token address
    /// @return Derived price = price(base) / price(quote), in 18 decimals
    function derivedPrice(address base, address quote) external view returns (uint256) {
        uint256 basePrice = _getPrice(base);
        uint256 quotePrice = _getPrice(quote);

        require(quotePrice > 0, "Zero quote price");

        // Both prices are in 18 decimals; dividing yields a ratio in 18 decimals
        return (basePrice * 1e18) / quotePrice;
    }

    /// @notice Internal price fetch with full validation
    /// @dev Validates round completeness, staleness against heartbeat, and positive price
    /// @param token Token address
    /// @return price Normalized price in 18 decimals
    function _getPrice(address token) internal view returns (uint256 price) {
        FeedConfig storage config = feeds[token];
        require(config.active, "Feed not active");

        (
            uint80 roundId,
            int256 answer,
            ,
            uint256 updatedAt,
            uint80 answeredInRound
        ) = config.feed.latestRoundData();

        // Round completeness: ensure answer is from the current round
        require(answeredInRound >= roundId, "Incomplete round");

        // Staleness check: reject if not updated within heartbeat
        require(block.timestamp - updatedAt <= config.heartbeat, "Stale price");

        // Negative price check: Chainlink can return negative values
        require(answer > 0, "Negative price");

        price = uint256(answer);

        // Normalize to 18 decimals
        uint8 feedDecimals = config.feed.decimals();
        if (feedDecimals < TARGET_DECIMALS) {
            price = price * (10 ** (TARGET_DECIMALS - feedDecimals));
        } else if (feedDecimals > TARGET_DECIMALS) {
            price = price / (10 ** (feedDecimals - TARGET_DECIMALS));
        }

        return price;
    }

    /// @notice Get feed configuration info for a token
    function getFeedInfo(address token) external view returns (
        address feedAddress,
        uint256 heartbeat,
        bool active
    ) {
        FeedConfig storage config = feeds[token];
        return (address(config.feed), config.heartbeat, config.active);
    }
}
