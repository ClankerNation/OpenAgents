// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../oracle/ChainlinkAdapter.sol";

contract MockAggregatorV3 is AggregatorV3Interface {
    uint8 private immutable feedDecimals;
    uint80 public roundId;
    int256 public answer;
    uint256 public startedAt;
    uint256 public updatedAt;
    uint80 public answeredInRound;

    constructor(uint8 decimals_, int256 answer_) {
        feedDecimals = decimals_;
        setRoundData(1, answer_, block.timestamp, 1);
    }

    function decimals() external view returns (uint8) {
        return feedDecimals;
    }

    function latestRoundData() external view returns (
        uint80,
        int256,
        uint256,
        uint256,
        uint80
    ) {
        return (roundId, answer, startedAt, updatedAt, answeredInRound);
    }

    function setRoundData(
        uint80 roundId_,
        int256 answer_,
        uint256 updatedAt_,
        uint80 answeredInRound_
    ) public {
        roundId = roundId_;
        answer = answer_;
        startedAt = updatedAt_;
        updatedAt = updatedAt_;
        answeredInRound = answeredInRound_;
    }
}
