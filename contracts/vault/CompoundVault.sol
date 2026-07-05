// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract CompoundVault is ReentrancyGuard {
    IERC20 public token;
    mapping(address => uint256) public deposits;
    
    event Compounded(address indexed user, uint256 rewards, uint256 timestamp);
    
    constructor(address _token) { token = IERC20(_token); }
    
    function compound() external nonReentrant {  // Fix #168
        uint256 balance = deposits[msg.sender];
        require(balance > 0, "No deposit");
        uint256 rewards = balance * 5 / 100;  // 5% APY
        deposits[msg.sender] += rewards;
        emit Compounded(msg.sender, rewards, block.timestamp);
    }
}
