// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IRandomLottery {
    function buyTicket() external payable;
    function claimPrizeTo(address payable recipient) external;
}

contract RejectEtherLotteryPlayer {
    function buyTicket(address lottery) external payable {
        IRandomLottery(lottery).buyTicket{value: msg.value}();
    }

    function claimPrizeTo(address lottery, address payable recipient) external {
        IRandomLottery(lottery).claimPrizeTo(recipient);
    }

    receive() external payable {
        revert("reject ether");
    }
}
