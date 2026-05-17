// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Contributor: Gaotax2006
// Platform: warpSpeed, opencode CLI
// Runtime: OS=win32 Arch=x64 Home=C:\Users\asus WorkDir=F:\ai-bounty-work\bounty-hunter\openagents Shell=powershell
// Date: 2026-05-17

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
/// @dev Wraps one or more Chainlink aggregators behind a simple getPrice interface,
///      with multi-hop derivation and stale-price protection
contract ChainlinkAdapter {
    address public admin;
    uint256 public constant TARGET_DECIMALS = 18;

    struct FeedConfig {
        AggregatorV3Interface feed;
        uint256 heartbeat;
        bool active;
    }

    mapping(address => FeedConfig) public feeds;
    mapping(address => address) public fallbackFeeds;

    event FeedRegistered(address indexed token, address feed, uint256 heartbeat);
    event FeedDeactivated(address indexed token);
    event FallbackFeedSet(address indexed token, address indexed fallback);

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

    function setFallbackFeed(address token, address fallback) external onlyAdmin {
        fallbackFeeds[token] = fallback;
        emit FallbackFeedSet(token, fallback);
    }

    function deactivateFeed(address token) external onlyAdmin {
        feeds[token].active = false;
        emit FeedDeactivated(token);
    }

    function _readFeed(address token) internal view returns (uint256 price, uint256 updatedAt) {
        FeedConfig storage config = feeds[token];
        require(config.active, "Feed not active");

        (uint80 roundId, int256 answer, , updatedAt, uint80 answeredInRound) =
            config.feed.latestRoundData();

        require(answer > 0, "Negative or zero price");
        require(answeredInRound >= roundId, "Round not complete");
        require(block.timestamp - updatedAt <= config.heartbeat, "Stale price");

        uint256 rawPrice = uint256(answer);
        uint8 feedDecimals = config.feed.decimals();
        if (feedDecimals < TARGET_DECIMALS) {
            rawPrice = rawPrice * 10 ** (TARGET_DECIMALS - feedDecimals);
        } else if (feedDecimals > TARGET_DECIMALS) {
            rawPrice = rawPrice / 10 ** (feedDecimals - TARGET_DECIMALS);
        }

        return (rawPrice, updatedAt);
    }

    function getPrice(address token) external view returns (uint256) {
        (uint256 price, ) = _readFeed(token);
        return price;
    }

    function getPriceWithFallback(address token) external view returns (uint256) {
        FeedConfig storage config = feeds[token];
        if (!config.active) {
            address fb = fallbackFeeds[token];
            require(fb != address(0), "No fallback");
            (uint256 p, ) = _readFeed(fb);
            return p;
        }
        try this.getPrice(token) returns (uint256 p) {
            return p;
        } catch {
            address fb = fallbackFeeds[token];
            require(fb != address(0), "No fallback");
            (uint256 p, ) = _readFeed(fb);
            return p;
        }
    }

    function derivedPrice(address base, address quote) external view returns (uint256) {
        (uint256 basePrice, ) = _readFeed(base);
        (uint256 quotePrice, ) = _readFeed(quote);
        require(quotePrice > 0, "Zero quote price");
        return (basePrice * 1e18) / quotePrice;
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
