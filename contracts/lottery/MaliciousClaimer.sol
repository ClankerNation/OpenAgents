// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title MaliciousClaimer
/// @notice A contract that attempts reentrancy on claimPrize
interface IPrizeSplit {
    function claimPrize(uint256 roundId) external;
}

contract MaliciousClaimer {
    address public prizeSplit;
    uint256 public targetRound;
    uint256 public callCount;
    uint256 public maxCalls;

    constructor(address _prizeSplit) {
        prizeSplit = _prizeSplit;
    }

    function attack(uint256 _roundId) external {
        targetRound = _roundId;
        maxCalls = 2; // Try to claim twice via reentrancy
        callCount = 0;
        IPrizeSplit(prizeSplit).claimPrize(_roundId);
    }

    receive() external payable {
        callCount++;
        if (callCount < maxCalls) {
            // Attempt reentrancy — should revert because claimed is already set
            IPrizeSplit(prizeSplit).claimPrize(targetRound);
        }
    }
}
