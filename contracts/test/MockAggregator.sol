// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Controllable mock of a Chainlink AggregatorV3Interface for testing
contract MockAggregator {
    int256 public answer;
    uint8 public decimals;
    uint80 public roundId;
    uint256 public updatedAt;
    uint80 public answeredInRound;

    function setRoundData(
        uint80 _roundId,
        int256 _answer,
        uint256 _updatedAt,
        uint80 _answeredInRound
    ) external {
        roundId = _roundId;
        answer = _answer;
        updatedAt = _updatedAt;
        answeredInRound = _answeredInRound;
    }

    function setDecimals(uint8 _decimals) external {
        decimals = _decimals;
    }

    function latestRoundData() external view returns (
        uint80,
        int256,
        uint256,
        uint256,
        uint80
    ) {
        return (roundId, answer, 0, updatedAt, answeredInRound);
    }
}
