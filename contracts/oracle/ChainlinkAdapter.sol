// @contributor rafaio1
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

    /// @notice Get the price for a token with full validation and fallback support.
    /// @param token The token address to get the price for.
    /// @return price The normalized price in 18 decimals.
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

        // Validate round completeness
        require(answeredInRound >= roundId, "ChainlinkAdapter: stale round");
        // Validate staleness against heartbeat
        require(block.timestamp - updatedAt <= config.heartbeat, "ChainlinkAdapter: stale price");
        // Validate positive price
        require(answer > 0, "ChainlinkAdapter: invalid price");

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

    /// @notice Get price with fallback to another token's feed if primary fails.
    /// @param token Primary token address.
    /// @param fallbackToken Fallback token address if primary is stale or invalid.
    /// @return price The normalized price in 18 decimals.
    function getPriceWithFallback(address token, address fallbackToken) external view returns (uint256) {
        FeedConfig storage config = feeds[token];
        if (config.active) {
            try this.getPrice(token) returns (uint256 price) {
                return price;
            } catch {}
        }
        // Fallback
        FeedConfig storage fbConfig = feeds[fallbackToken];
        require(fbConfig.active, "ChainlinkAdapter: fallback not active");

        (
            uint80 roundId,
            int256 answer,
            /* uint256 startedAt */,
            uint256 updatedAt,
            uint80 answeredInRound
        ) = fbConfig.feed.latestRoundData();

        require(answeredInRound >= roundId, "ChainlinkAdapter: fallback stale round");
        require(block.timestamp - updatedAt <= fbConfig.heartbeat, "ChainlinkAdapter: fallback stale price");
        require(answer > 0, "ChainlinkAdapter: fallback invalid price");

        uint256 price = uint256(answer);
        uint8 feedDecimals = fbConfig.feed.decimals();
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
