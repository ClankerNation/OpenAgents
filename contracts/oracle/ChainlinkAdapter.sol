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

        require(roundId == answeredInRound, "Round incomplete");
        require(updatedAt >= block.timestamp - config.heartbeat, "Feed stale");
        require(answer >= 0, "Negative price");

        uint256 price = uint256(answer);

        uint8 feedDecimals = config.feed.decimals();
        if (feedDecimals < TARGET_DECIMALS) {
            price = price * (10 ** (TARGET_DECIMALS - feedDecimals));
        } else if (feedDecimals > TARGET_DECIMALS) {
            price = price / (10 ** (feedDecimals - TARGET_DECIMALS));
        }

        return price;
    }

    /// @notice Derive price for a token pair using two Chainlink feeds via USD
    /// @dev base/quote = (base/USD) / (quote/USD)
    function derivedPrice(address base, address quote) external view returns (uint256) {
        require(base != quote, "Same token");
        require(feeds[base].active && feeds[quote].active, "Feed not active");

        (, int256 baseAnswer,, uint256 baseUpdatedAt, uint80 baseAnsweredInRound) = feeds[base].feed.latestRoundData();
        (, int256 quoteAnswer,, uint256 quoteUpdatedAt, uint80 quoteAnsweredInRound) = feeds[quote].feed.latestRoundData();

        require(baseAnsweredInRound == baseAnsweredInRound, "Base round incomplete");
        require(quoteAnsweredInRound == quoteAnsweredInRound, "Quote round incomplete");
        require(baseUpdatedAt >= block.timestamp - feeds[base].heartbeat, "Base feed stale");
        require(quoteUpdatedAt >= block.timestamp - feeds[quote].heartbeat, "Quote feed stale");
        require(baseAnswer > 0 && quoteAnswer > 0, "Invalid answer");

        uint256 baseNormalized = _normalize(uint256(baseAnswer), feeds[base].feed.decimals());
        uint256 quoteNormalized = _normalize(uint256(quoteAnswer), feeds[quote].feed.decimals());

        return baseNormalized * 1e18 / quoteNormalized;
    }

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
