// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../PrizeSplit.sol";

contract RejectEtherWinner {
    function claim(PrizeSplit prizeSplit, uint256 roundId) external {
        prizeSplit.claimPrize(roundId);
    }

    receive() external payable {
        revert("reject ether");
    }
}
