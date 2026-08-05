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
/**
 * @custom:contributor CodexBaseUSDCHunter
 * @custom:date 2026-08-05
 * @custom:runtime darwin/arm64; shell /bin/zsh
 * @custom:note Private session initialization text is intentionally omitted.
 */
contract ChainlinkAdapter {
    address public admin;
    uint256 public constant TARGET_DECIMALS = 18;

    struct FeedConfig {
        AggregatorV3Interface feed;
        uint256 heartbeat; // max seconds between updates
        bool active;
    }

    struct FallbackConfig {
        AggregatorV3Interface feed;
        uint256 heartbeat;
        bool active;
    }

    mapping(address => FeedConfig) public feeds;
    mapping(address => FallbackConfig) public fallbackFeeds;

    event FeedRegistered(address indexed token, address feed, uint256 heartbeat);
    event FeedDeactivated(address indexed token);
    event FallbackFeedRegistered(address indexed token, address feed, uint256 heartbeat);
    event FallbackFeedCleared(address indexed token);

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
        require(token != address(0), "Invalid token");
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

    function setFallbackFeed(
        address token,
        address feed,
        uint256 heartbeat
    ) external onlyAdmin {
        require(token != address(0), "Invalid token");
        require(feed != address(0), "Invalid feed");
        require(heartbeat > 0, "Invalid heartbeat");

        fallbackFeeds[token] = FallbackConfig({
            feed: AggregatorV3Interface(feed),
            heartbeat: heartbeat,
            active: true
        });

        emit FallbackFeedRegistered(token, feed, heartbeat);
    }

    function clearFallbackFeed(address token) external onlyAdmin {
        delete fallbackFeeds[token];
        emit FallbackFeedCleared(token);
    }

    function getPrice(address token) external view returns (uint256) {
        FeedConfig storage config = feeds[token];
        require(config.active, "Feed not active");

        (bool valid, uint256 price) = _readFeed(config.feed, config.heartbeat);
        if (valid) {
            return price;
        }

        FallbackConfig storage fallbackConfig = fallbackFeeds[token];
        (valid, price) = _readFeed(fallbackConfig.feed, fallbackConfig.heartbeat);
        require(valid && fallbackConfig.active, "No valid feed");
        return price;
    }

    function _readFeed(
        AggregatorV3Interface feed,
        uint256 heartbeat
    ) internal view returns (bool valid, uint256 normalizedPrice) {
        if (address(feed) == address(0) || heartbeat == 0) {
            return (false, 0);
        }

        try feed.latestRoundData() returns (
            uint80 roundId,
            int256 answer,
            uint256 startedAt,
            uint256 updatedAt,
            uint80 answeredInRound
        ) {
            startedAt;
            if (
                roundId == 0 ||
                answeredInRound < roundId ||
                answer <= 0 ||
                updatedAt == 0 ||
                updatedAt > block.timestamp ||
                block.timestamp - updatedAt > heartbeat
            ) {
                return (false, 0);
            }

            try feed.decimals() returns (uint8 feedDecimals) {
                uint256 price = uint256(answer);
                if (feedDecimals < TARGET_DECIMALS) {
                    price *= 10 ** (TARGET_DECIMALS - feedDecimals);
                } else if (feedDecimals > TARGET_DECIMALS) {
                    price /= 10 ** (feedDecimals - TARGET_DECIMALS);
                }
                return (true, price);
            } catch {
                return (false, 0);
            }
        } catch {
            return (false, 0);
        }
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
        FallbackConfig storage config = fallbackFeeds[token];
        return (address(config.feed), config.heartbeat, config.active);
    }
}
