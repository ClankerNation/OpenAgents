// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * @contributor Codex Agent xyjk0511
 * @platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
 * @runtime Microsoft Windows 10.0.22631, X64, redacted local paths, shell PowerShell 7.6.2
 * @date 2026-05-31T00:00:00-07:00
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

interface FallbackOracleInterface {
    function getPrice(address token) external view returns (uint256);
}

/// @title ChainlinkAdapter
/// @notice Adapter for Chainlink price feeds with normalized 18-decimal output
/// @dev Wraps one or more Chainlink aggregators behind a simple getPrice interface
contract ChainlinkAdapter {
    address public admin;
    address public fallbackOracle;
    uint256 public constant TARGET_DECIMALS = 18;

    struct FeedConfig {
        AggregatorV3Interface feed;
        uint256 heartbeat; // max seconds between updates
        bool active;
    }

    mapping(address => FeedConfig) public feeds;

    event FeedRegistered(address indexed token, address feed, uint256 heartbeat);
    event FeedDeactivated(address indexed token);
    event FallbackOracleUpdated(address indexed fallbackOracle);

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

    function setFallbackOracle(address oracle) external onlyAdmin {
        require(oracle != address(this), "Invalid fallback");
        fallbackOracle = oracle;
        emit FallbackOracleUpdated(oracle);
    }

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

        require(answeredInRound >= roundId, "Incomplete round");
        require(answer > 0, "Invalid price");

        if (updatedAt == 0 || block.timestamp > updatedAt + config.heartbeat) {
            return _fallbackPrice(token);
        }

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

    function _fallbackPrice(address token) internal view returns (uint256) {
        require(fallbackOracle != address(0), "Stale price");
        uint256 price = FallbackOracleInterface(fallbackOracle).getPrice(token);
        require(price > 0, "Invalid fallback price");
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
