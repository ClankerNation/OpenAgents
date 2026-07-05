// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract FlashLoanReceiver is ReentrancyGuard {
    address public lendingPool;
    
    event FlashLoanExecuted(address indexed borrower, address indexed token, uint256 amount, uint256 fee);
    
    constructor(address _pool) { lendingPool = _pool; }
    
    function executeOperation(address token, uint256 amount, uint256 premium, address initiator) external nonReentrant returns (bool) {
        require(msg.sender == lendingPool, "Only pool");
        // Arbitrage or liquidation logic here
        // ...
        // Repay loan + premium
        IERC20(token).approve(lendingPool, amount + premium);
        emit FlashLoanExecuted(initiator, token, amount, premium);
        return true;
    }
}
