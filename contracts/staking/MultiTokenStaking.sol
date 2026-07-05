// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract MultiTokenStaking is ReentrancyGuard {
    mapping(address => bool) public supportedTokens;
    mapping(address => mapping(address => uint256)) public stakes;  // user -> token -> amount
    
    event EmergencyWithdraw(address indexed user, address indexed token, uint256 amount, uint256 timestamp);
    
    function emergencyWithdraw(address token) external nonReentrant {
        uint256 balance = IERC20(token).balanceOf(address(this));
        require(balance > 0, "No balance to withdraw");  // Fix #195
        require(supportedTokens[token], "Token not supported");  // Fix #195
        IERC20(token).transfer(msg.sender, balance);
        emit EmergencyWithdraw(msg.sender, token, balance, block.timestamp);
    }
}
