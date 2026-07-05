// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract RandomLottery {
    enum DrawStatus { Active, Completed, Cancelled }
    struct Draw {
        uint256 id;
        address token;
        DrawStatus status;
        mapping(address => uint256) participants;
    }
    
    mapping(uint256 => Draw) public draws;
    
    event Refunded(uint256 indexed drawId, address indexed user, uint256 amount);
    
    function refundCancelledDraw(uint256 drawId) external {
        Draw storage d = draws[drawId];
        require(d.status == DrawStatus.Cancelled, "Not cancelled");  // Fix #176
        uint256 refund = d.participants[msg.sender];
        require(refund > 0, "Nothing to refund");  // Fix #176
        d.participants[msg.sender] = 0;
        IERC20(d.token).transfer(msg.sender, refund);
        emit Refunded(drawId, msg.sender, refund);
    }
}
