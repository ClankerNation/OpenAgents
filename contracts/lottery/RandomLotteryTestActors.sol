// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IRandomLotteryTicket {
    function buyTicket() external payable;
}

/// @dev Test actor whose fallback rejects ETH, exercising the pull-payment path.
contract RejectingWinner {
    function buyTicket(address lottery) external payable {
        IRandomLotteryTicket(lottery).buyTicket{value: msg.value}();
    }
}
