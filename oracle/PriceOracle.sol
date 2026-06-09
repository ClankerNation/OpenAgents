// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

interface AggregatorV3Interface {
    function latestRoundData() external view returns (
        uint80 roundId, int256 answer, uint256 startedAt,
        uint256 updatedAt, uint80 answeredInRound
    );
    function decimals() external view returns (uint8);
}

contract ArenaOracle {
    mapping(address => AggregatorV3Interface) public feeds;
    address public owner;
    uint256 public maxStaleness = 3600;

    event FeedUpdated(address indexed token, address feed);
    event PriceQueried(address indexed token, int256 price);

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    function setFeed(address token, address feed) external onlyOwner {
        feeds[token] = AggregatorV3Interface(feed);
        emit FeedUpdated(token, feed);
    }

    function getPrice(address token) external view returns (int256 price, uint8 decimals) {
        AggregatorV3Interface feed = feeds[token];
        require(address(feed) != address(0), "No feed");

        (, price,, uint256 updatedAt,) = feed.latestRoundData();
        require(block.timestamp - updatedAt <= maxStaleness, "Stale price");
        require(price > 0, "Invalid price");

        decimals = feed.decimals();
        emit PriceQueried(token, price);
    }

    function setMaxStaleness(uint256 _seconds) external onlyOwner {
        maxStaleness = _seconds;
    }
}
