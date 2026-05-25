// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../lottery/PrizeSplit.sol";

contract RejectEtherWinner {
    function claim(PrizeSplit prizeSplit, uint256 roundId) external {
        prizeSplit.claim(roundId);
    }
}
