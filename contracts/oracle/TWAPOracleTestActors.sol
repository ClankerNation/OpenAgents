// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface ITWAPOracleRecorder {
    function recordObservation(uint256 spotPrice) external;
}

/// @dev Calls the oracle twice in one transaction to verify the block guard.
contract SameBlockRecorder {
    function recordTwice(address oracle, uint256 firstPrice, uint256 secondPrice) external {
        ITWAPOracleRecorder(oracle).recordObservation(firstPrice);
        ITWAPOracleRecorder(oracle).recordObservation(secondPrice);
    }
}
