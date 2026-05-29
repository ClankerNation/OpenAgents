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
        return _getNormalizedPrice(token);
    }

    function pairKey(address base, address quote) public pure returns (address) {
        return address(uint160(uint256(keccak256(abi.encodePacked(base, quote)))));
    }

    function derivedPrice(address base, address quote) external view returns (uint256) {
        if (base == quote) {
            return 10 ** TARGET_DECIMALS;
        }

        uint256 directPrice = _tryGetNormalizedPrice(pairKey(base, quote));
        if (directPrice != 0) {
            return directPrice;
        }

        if (!feeds[quote].active) {
            return _getNormalizedPrice(base);
        }

        uint256 basePrice = _getNormalizedPrice(base);
        uint256 quotePrice = _getNormalizedPrice(quote);
        return (basePrice * (10 ** TARGET_DECIMALS)) / quotePrice;
    }

    function _tryGetNormalizedPrice(address token) internal view returns (uint256) {
        FeedConfig storage config = feeds[token];
        if (!config.active) {
            return 0;
        }
        return _readNormalizedPrice(config);
    }

    function _getNormalizedPrice(address token) internal view returns (uint256) {
        FeedConfig storage config = feeds[token];
        require(config.active, "Feed not active");
        return _readNormalizedPrice(config);
    }

    function _readNormalizedPrice(FeedConfig storage config) internal view returns (uint256 price) {
        (
            uint80 roundId,
            int256 answer,
            /* uint256 startedAt */,
            uint256 updatedAt,
            uint80 answeredInRound
        ) = config.feed.latestRoundData();

        require(answer > 0, "Invalid price");
        require(updatedAt > 0 && updatedAt <= block.timestamp, "Invalid timestamp");
        require(answeredInRound >= roundId, "Incomplete round");
        require(block.timestamp - updatedAt <= config.heartbeat, "Stale price");

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

    function getFeedInfo(address token) external view returns (
        address feedAddress,
        uint256 heartbeat,
        bool active
    ) {
        FeedConfig storage config = feeds[token];
        return (address(config.feed), config.heartbeat, config.active);
    }
}
