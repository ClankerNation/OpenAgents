// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MockChainlinkFeed {
    uint8 public immutable feedDecimals;
    uint80 private roundId;
    int256 private answer;
    uint256 private startedAt;
    uint256 private updatedAt;
    uint80 private answeredInRound;
    bool public shouldRevert;

    constructor(uint8 decimals_) {
        feedDecimals = decimals_;
    }

    function setRoundData(
        uint80 roundId_,
        int256 answer_,
        uint256 startedAt_,
        uint256 updatedAt_,
        uint80 answeredInRound_,
        bool shouldRevert_
    ) external {
        roundId = roundId_;
        answer = answer_;
        startedAt = startedAt_;
        updatedAt = updatedAt_;
        answeredInRound = answeredInRound_;
        shouldRevert = shouldRevert_;
    }

    function latestRoundData() external view returns (
        uint80,
        int256,
        uint256,
        uint256,
        uint80
    ) {
        require(!shouldRevert, "mock feed reverted");
        return (roundId, answer, startedAt, updatedAt, answeredInRound);
    }

    function decimals() external view returns (uint8) {
        require(!shouldRevert, "mock feed reverted");
        return feedDecimals;
    }
}
