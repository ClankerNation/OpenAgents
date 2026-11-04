// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IPrizeSplit2 {
    function claimPrize(uint256 roundId) external;
}

/// @notice Re-enters claimPrize from receive(), so it would double-claim without CEI ordering.
contract ReentrantWinner {
    IPrizeSplit2 public immutable split;
    uint256 public depth;

    constructor(address _split) {
        split = IPrizeSplit2(_split);
    }

    function claim(uint256 roundId) external {
        split.claimPrize(roundId);
    }

    receive() external payable {
        if (depth < 1) {
            depth++;
            try split.claimPrize(1) {} catch {}
        }
    }
}
