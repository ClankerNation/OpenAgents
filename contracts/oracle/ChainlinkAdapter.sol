// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor-info rafaio1
 * @timestamp 2026-08-20T10:35:00Z
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

    // BUG: No roundId completeness check — answeredInRound should equal roundId to
    // confirm the answer is from the current round; without this check, the contract
    // may return an answer from a previous round that hasn't been updated
    // BUG: Stale price allowed — updatedAt is not checked against the heartbeat,
    // so a feed that hasn't updated in days will still return the last known price
    // BUG: Negative price not rejected — Chainlink can return negative prices for
    // certain feeds; casting a negative int256 to uint256 produces a huge incorrect value
    function getPrice(address token) external view returns (uint256) {
        FeedConfig storage config = feeds[token];
        require(config.active, "Feed not active");

        (
            uint80 roundId,
            int256 answer,
            uint256 startedAt,
            uint256 updatedAt,
            uint80 answeredInRound
        ) = config.feed.latestRoundData();

        require(answeredInRound >= roundId, "Stale round data");
        require(block.timestamp - updatedAt <= config.heartbeat, "Price stale");
        require(answer > 0, "Invalid negative price");

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

    /**
     * @notice Derive price for base/quote pair using two feeds when direct feed unavailable
     * @param base The base token address (e.g., TOKEN)
     * @param quote The quote token address (e.g., ETH)
     * @return price Normalized 18-decimal price of base in terms of quote
     */
    function derivedPrice(address base, address quote) external view returns (uint256 price) {
        FeedConfig storage baseConfig = feeds[base];
        FeedConfig storage quoteConfig = feeds[quote];
        
        require(baseConfig.active, "Base feed not active");
        require(quoteConfig.active, "Quote feed not active");
        
        // Get base feed data with validation
        (
            uint80 baseRoundId,
            int256 baseAnswer,
            ,
            uint256 baseUpdatedAt,
            uint80 baseAnsweredInRound
        ) = baseConfig.feed.latestRoundData();
        
        require(baseAnsweredInRound >= baseRoundId, "Base stale round");
        require(block.timestamp - baseUpdatedAt <= baseConfig.heartbeat, "Base price stale");
        require(baseAnswer > 0, "Invalid base price");
        
        // Get quote feed data with validation
        (
            uint80 quoteRoundId,
            int256 quoteAnswer,
            ,
            uint256 quoteUpdatedAt,
            uint80 quoteAnsweredInRound
        ) = quoteConfig.feed.latestRoundData();
        
        require(quoteAnsweredInRound >= quoteRoundId, "Quote stale round");
        require(block.timestamp - quoteUpdatedAt <= quoteConfig.heartbeat, "Quote price stale");
        require(quoteAnswer > 0, "Invalid quote price");
        
        // Normalize both to 18 decimals before division
        uint256 basePrice = uint256(baseAnswer);
        uint8 baseDecimals = baseConfig.feed.decimals();
        if (baseDecimals < TARGET_DECIMALS) {
            basePrice = basePrice * (10 ** (TARGET_DECIMALS - baseDecimals));
        } else if (baseDecimals > TARGET_DECIMALS) {
            basePrice = basePrice / (10 ** (baseDecimals - TARGET_DECIMALS));
        }
        
        uint256 quotePrice = uint256(quoteAnswer);
        uint8 quoteDecimals = quoteConfig.feed.decimals();
        if (quoteDecimals < TARGET_DECIMALS) {
            quotePrice = quotePrice * (10 ** (TARGET_DECIMALS - quoteDecimals));
        } else if (quoteDecimals > TARGET_DECIMALS) {
            quotePrice = quotePrice / (10 ** (quoteDecimals - TARGET_DECIMALS));
        }
        
        // Calculate derived price: base/quote with 18 decimal precision
        price = (basePrice * (10 ** TARGET_DECIMALS)) / quotePrice;
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
