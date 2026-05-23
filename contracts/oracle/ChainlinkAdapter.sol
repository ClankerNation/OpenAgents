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
        uint256 heartbeat;
        bool active;
    }

    struct DerivedFeed {
        address baseToken;
        address quoteToken;
        bool active;
    }

    mapping(address => FeedConfig) public feeds;
    mapping(bytes32 => DerivedFeed) public derivedFeeds;

    event FeedRegistered(address indexed token, address feed, uint256 heartbeat);
    event FeedDeactivated(address indexed token);
    event DerivedFeedRegistered(bytes32 indexed feedId, address baseToken, address quoteToken);

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

    function registerDerivedFeed(address baseToken, address quoteToken) external onlyAdmin {
        require(feeds[baseToken].active, "Base feed not active");
        require(feeds[quoteToken].active, "Quote feed not active");
        bytes32 feedId = keccak256(abi.encodePacked(baseToken, quoteToken));
        derivedFeeds[feedId] = DerivedFeed({
            baseToken: baseToken,
            quoteToken: quoteToken,
            active: true
        });
        emit DerivedFeedRegistered(feedId, baseToken, quoteToken);
    }

    function getDerivedPrice(address baseToken, address quoteToken) external view returns (uint256) {
        bytes32 feedId = keccak256(abi.encodePacked(baseToken, quoteToken));
        require(derivedFeeds[feedId].active, "Derived feed not active");

        uint256 basePrice = _getRawPrice(baseToken);
        uint256 quotePrice = _getRawPrice(quoteToken);
        require(quotePrice > 0, "Zero quote price");

        return (basePrice * PRECISION) / quotePrice;
    }

    function _getRawPrice(address token) internal view returns (uint256) {
        FeedConfig storage config = feeds[token];
        require(config.active, "Feed not active");

        (, int256 answer, , , ) = config.feed.latestRoundData();
        require(answer > 0, "Negative price");

        uint256 price = uint256(answer);
        uint8 feedDecimals = config.feed.decimals();
        if (feedDecimals < TARGET_DECIMALS) {
            price = price * (10 ** (TARGET_DECIMALS - feedDecimals));
        } else if (feedDecimals > TARGET_DECIMALS) {
            price = price / (10 ** (feedDecimals - TARGET_DECIMALS));
        }
        return price;
    }

    // BUG: No roundId completeness check — answeredInRound should equal roundId to
    // confirm the answer is from the current round; without this check, the contract
    // may return an answer from a previous round that hasn't been updated
    // BUG: Stale price allowed — updatedAt is not checked against the heartbeat,
    // so a feed that hasn't updated in days will still return the last known price
    // BUG: Negative price not rejected — Chainlink can return negative prices for
    // certain feeds; casting a negative int256 to uint256 produces a huge incorrect value
    function getPrice(address token) external view returns (uint256) {
        return _getRawPrice(token);
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
