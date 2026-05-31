// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IPrizeSplit {
    function claimPrizeTo(uint256 _roundId, address payable recipient) external;
}

contract NonPayableWinner {
    function claimTo(address prizeSplit, uint256 roundId, address payable recipient) external {
        IPrizeSplit(prizeSplit).claimPrizeTo(roundId, recipient);
    }
}
