// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/Address.sol";

interface AggregatorV3Interface {
    function latestRoundData() external view returns (
        uint80 roundId,
        int256 answer,
        uint256 startedAt,
        uint256 updatedAt,
        uint80 answeredInRound
    );
}

contract ChainlinkAdapter {
    struct FeedConfig {
        address feed;
        uint256 minAnswer;
        uint256 maxAnswer;
        uint40 heartbeat;
        bool active;
    }

    mapping(address => FeedConfig) public feeds;

    event FeedConfigured(address indexed token, address feed, uint256 min, uint256 max);

    function configureFeed(
        address token,
        address feed,
        uint256 minAnswer,
        uint256 maxAnswer,
        uint40 heartbeat
    ) external {
        feeds[token] = FeedConfig({
            feed: feed,
            minAnswer: minAnswer,
            maxAnswer: maxAnswer,
            heartbeat: heartbeat,
            active: true
        });
        emit FeedConfigured(token, feed, minAnswer, maxAnswer);
    }

    function deactivateFeed(address token) external {
        feeds[token].active = false;
    }

    function getPrice(address token) external view returns (uint256) {
        FeedConfig storage config = feeds[token];
        require(config.active, "Feed not active");

        AggregatorV3Interface feed = AggregatorV3Interface(config.feed);
        (
            uint80 roundId,
            int256 answer,
            uint256 startedAt,
            uint256 updatedAt,
            uint80 answeredInRound
        ) = feed.latestRoundData();

        require(answer > 0, "Negative price");
        require(answer >= 0, "Negative price");
        
        uint256 price = uint256(answer);

        // Validate against configured bounds
        require(price >= config.minAnswer, "Price below minimum");
        require(price <= config.maxAnswer, "Price above maximum");
        
        // Check staleness
        require(block.timestamp - updatedAt <= config.heartbeat, "Stale price");

        return price;
    }

    function getFeedConfig(address token) external view returns (FeedConfig memory) {
        return feeds[token];
    }
}
