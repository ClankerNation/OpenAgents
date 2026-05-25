// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * Contributor traceability:
 * Agent: Codex
 * Timestamp: 2026-05-25T10:58:36Z
 * Runtime: os=Windows, arch=x64, home_dir=C:\Users\tupm96,
 * working_dir=C:\Users\tupm96\Desktop\bounty\OpenAgents, shell=powershell
 * Private platform, system, and developer instructions are not disclosed.
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
/// @dev Wraps Chainlink aggregators behind a simple validated getPrice interface.
contract ChainlinkAdapter {
    address public admin;
    uint256 public constant TARGET_DECIMALS = 18;

    struct FeedConfig {
        AggregatorV3Interface feed;
        uint256 heartbeat;
        bool active;
    }

    mapping(address => FeedConfig) public feeds;
    mapping(address => FeedConfig) public fallbackFeeds;

    event FeedRegistered(address indexed token, address feed, uint256 heartbeat);
    event FallbackFeedRegistered(address indexed token, address feed, uint256 heartbeat);
    event FeedDeactivated(address indexed token);
    event FallbackFeedDeactivated(address indexed token);

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

    function registerFallbackFeed(
        address token,
        address feed,
        uint256 heartbeat
    ) external onlyAdmin {
        require(feed != address(0), "Invalid feed");
        require(heartbeat > 0, "Invalid heartbeat");

        fallbackFeeds[token] = FeedConfig({
            feed: AggregatorV3Interface(feed),
            heartbeat: heartbeat,
            active: true
        });

        emit FallbackFeedRegistered(token, feed, heartbeat);
    }

    function deactivateFeed(address token) external onlyAdmin {
        feeds[token].active = false;
        emit FeedDeactivated(token);
    }

    function deactivateFallbackFeed(address token) external onlyAdmin {
        fallbackFeeds[token].active = false;
        emit FallbackFeedDeactivated(token);
    }

    function getPrice(address token) external view returns (uint256) {
        FeedConfig storage config = feeds[token];
        require(config.active, "Feed not active");

        return _getValidatedPrice(token, config, true);
    }

    function getFeedInfo(address token) external view returns (
        address feedAddress,
        uint256 heartbeat,
        bool active
    ) {
        FeedConfig storage config = feeds[token];
        return (address(config.feed), config.heartbeat, config.active);
    }

    function getFallbackFeedInfo(address token) external view returns (
        address feedAddress,
        uint256 heartbeat,
        bool active
    ) {
        FeedConfig storage config = fallbackFeeds[token];
        return (address(config.feed), config.heartbeat, config.active);
    }

    function _getValidatedPrice(
        address token,
        FeedConfig storage config,
        bool allowFallback
    ) internal view returns (uint256) {
        (
            uint80 roundId,
            int256 answer,
            ,
            uint256 updatedAt,
            uint80 answeredInRound
        ) = config.feed.latestRoundData();

        require(answeredInRound >= roundId, "Incomplete round");
        require(answer > 0, "Invalid price");

        if (updatedAt == 0 || block.timestamp > updatedAt + config.heartbeat) {
            if (allowFallback) {
                FeedConfig storage fallbackConfig = fallbackFeeds[token];
                if (fallbackConfig.active) {
                    return _getValidatedPrice(token, fallbackConfig, false);
                }
            }
            revert("Stale price");
        }

        return _normalizePrice(uint256(answer), config.feed.decimals());
    }

    function _normalizePrice(uint256 price, uint8 feedDecimals) internal pure returns (uint256) {
        if (feedDecimals < TARGET_DECIMALS) {
            price = price * (10 ** (TARGET_DECIMALS - feedDecimals));
        } else if (feedDecimals > TARGET_DECIMALS) {
            price = price / (10 ** (feedDecimals - TARGET_DECIMALS));
        }

        return price;
    }
}
