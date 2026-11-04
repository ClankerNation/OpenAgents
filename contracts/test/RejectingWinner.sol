// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IPrizeSplit {
    function claimPrize(uint256 roundId) external;
}

/// @notice A winner contract with no receive/fallback, so a plain ETH transfer to it reverts.
contract RejectingWinner {
    IPrizeSplit public immutable split;

    constructor(address _split) {
        split = IPrizeSplit(_split);
    }

    function claim(uint256 roundId) external {
        split.claimPrize(roundId);
    }
}
