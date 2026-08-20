// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor rafaio1
 * @timestamp 2026-08-20T02:30:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */


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

    /// @notice Get validated price for a token with direct feed.
    /// @param token Address of the token.
    /// @return Normalized price in 18 decimals.
    function getPrice(address token) external view returns (uint256) {
        return _getValidatedPrice(token);
    }

    /// @notice Get derived price for a pair without direct feed.
    /// @dev Calculates base/quote using two feeds: price = baseFeed / quoteFeed.
    ///      Handles decimal normalization between feeds. Checks staleness on both.
    /// @param base Base token address (e.g., TOKEN).
    /// @param quote Quote token address (e.g., ETH).
    /// @return Derived price normalized to 18 decimals.
    function derivedPrice(address base, address quote) external view returns (uint256) {
        // Try direct feed first
        if (feeds[base].active && !feeds[quote].active) {
            return _getValidatedPrice(base);
        }

        // Both must have active feeds for derivation
        require(feeds[base].active, "Base feed not active");
        require(feeds[quote].active, "Quote feed not active");

        uint256 basePrice = _getValidatedPrice(base);
        uint256 quotePrice = _getValidatedPrice(quote);

        require(quotePrice > 0, "Quote price zero");

        // basePrice and quotePrice are both 18 decimals
        // derived = basePrice / quotePrice * 1e18
        return (basePrice * 1e18) / quotePrice;
    }

    /// @internal Validate and normalize a single feed price.
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

        // Round completeness check
        require(answeredInRound >= roundId, "Stale round");
        // Staleness check
        require(block.timestamp - updatedAt <= config.heartbeat, "Price stale");
        // Negative price check
        require(answer > 0, "Invalid price");

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
