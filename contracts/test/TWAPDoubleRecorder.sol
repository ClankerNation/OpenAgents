// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface ITWAPOracle {
    function recordObservation(uint256 spotPrice) external;
}

contract TWAPDoubleRecorder {
    function recordTwice(ITWAPOracle oracle, uint256 firstPrice, uint256 secondPrice) external {
        oracle.recordObservation(firstPrice);
        oracle.recordObservation(secondPrice);
    }
}
