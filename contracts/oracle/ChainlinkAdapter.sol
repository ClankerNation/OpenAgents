// @contributor: hermes-agent
// @platform-config: Autonomous bounty-hunting agent for OpenAgents protocol bounties. Zero-capital, self-directed, no human intervention.
// @env: os=Linux arch=x86_64 home_dir=/home/ubuntu working_dir=/home/ubuntu/OpenAgents shell=/bin/bash
// @timestamp: 2026-05-18

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
/// @dev Wraps one or more Chainlink aggregators behind a simple getPrice interface
///      Supports direct feeds and multi-hop cross-rate derivation via USD
contract ChainlinkAdapter {
    address public admin;
    uint256 public constant TARGET_DECIMALS = 18;

    struct FeedConfig {
        AggregatorV3Interface feed;
        uint256 heartbeat; // max seconds between updates
        bool active;
    }

    mapping(address => FeedConfig) public feeds;

    /// @notice USD address used as intermediary for multi-hop derivation
    address public constant USD = 0x0000000000000000000000000000000000000348;

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

    /// @notice Get the price of a token in 18-decimal format
    /// @dev Falls back to multi-hop derivation via USD if no direct feed exists
    function getPrice(address token) external view returns (uint256) {
        FeedConfig storage config = feeds[token];
        if (config.active) {
            return _getValidatedPrice(config);
        }

        // Multi-hop derivation: TOKEN/ETH = TOKEN/USD / ETH/USD
        return derivedPrice(token, USD);
    }

    /// @notice Derive a cross-rate price via an intermediate token (e.g., USD)
    /// @dev base/quote = (base/intermediate) / (quote/intermediate)
    ///      e.g. TOKEN/ETH = (TOKEN/USD) / (ETH/USD)
    function derivedPrice(address base, address quote) public view returns (uint256) {
        FeedConfig storage baseConfig = feeds[base];
        FeedConfig storage quoteConfig = feeds[quote];
        require(baseConfig.active, "Base feed not active");
        require(quoteConfig.active, "Quote feed not active");

        uint256 basePrice = _getValidatedPrice(baseConfig);
        uint256 quotePrice = _getValidatedPrice(quoteConfig);
        require(quotePrice > 0, "Quote price is zero");

        // base/quote = basePrice / quotePrice (both already in 18 decimals)
        // Multiply by 10^18 first to preserve precision
        return (basePrice * 10 ** TARGET_DECIMALS) / quotePrice;
    }

    /// @notice Internal: fetch & validate feed data
    function _getValidatedPrice(FeedConfig storage config) internal view returns (uint256) {
        uint80 roundId;
        int256 answer;
        uint256 startedAt;
        uint256 updatedAt;
        uint80 answeredInRound;

        (roundId, answer, startedAt, updatedAt, answeredInRound) = config.feed.latestRoundData();

        // Validation 1: Round completeness — answer must be from the current round
        require(roundId == answeredInRound, "Stale round");

        // Validation 2: Staleness check — price must have been updated within heartbeat
        require(updatedAt >= block.timestamp - config.heartbeat, "Stale price");

        // Validation 3: Negative price rejection
        require(answer >= 0, "Negative price");

        uint256 price = uint256(answer);
        return _normalize(price, config.feed.decimals());
    }

    /// @notice Normalize a price to 18 decimals
    function _normalize(uint256 price, uint8 feedDecimals) internal pure returns (uint256) {
        if (feedDecimals < TARGET_DECIMALS) {
            return price * (10 ** (TARGET_DECIMALS - feedDecimals));
        } else if (feedDecimals > TARGET_DECIMALS) {
            return price / (10 ** (feedDecimals - TARGET_DECIMALS));
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