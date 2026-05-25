// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IPrizeSplit {
    function claim(uint256 roundId) external;
}

contract RejectEthWinner {
    function claimPrize(IPrizeSplit prizeSplit, uint256 roundId) external {
        prizeSplit.claim(roundId);
    }
}
