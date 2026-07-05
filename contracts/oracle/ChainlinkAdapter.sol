// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@chainlink/contracts/src/v0.8/interfaces/AggregatorV3Interface.sol";

contract ChainlinkAdapter {
    mapping(bytes32 => AggregatorV3Interface) public feeds;  // symbol => feed
    mapping(bytes32 => uint256) public timestamps;
    
    event PriceUpdated(bytes32 indexed symbol, uint256 price, uint256 timestamp);
    
    function addFeed(bytes32 symbol, address feed) external {
        feeds[symbol] = AggregatorV3Interface(feed);  // Fix #133: multi-feed
    }
    
    function getPrice(bytes32 symbol) external returns (uint256) {
        AggregatorV3Interface feed = feeds[symbol];
        require(address(feed) != address(0), "Feed not found");
        (, int256 price, , uint256 updatedAt, ) = feed.latestRoundData();
        require(block.timestamp - updatedAt < 3600, "Stale price");
        timestamps[symbol] = block.timestamp;
        emit PriceUpdated(symbol, uint256(price), block.timestamp);
        return uint256(price);
    }
    
    function getMultiplePrices(bytes32[] calldata symbols) external returns (uint256[] memory) {
        uint256[] memory prices = new uint256[](symbols.length);
        for (uint i = 0; i < symbols.length; i++) {
            prices[i] = this.getPrice(symbols[i]);  // Fix #133
        }
        return prices;
    }
}
