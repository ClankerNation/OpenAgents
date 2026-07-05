// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract LendingPool {
    IERC20 public token;
    mapping(address => uint256) public deposits;
    mapping(address => uint256) public borrows;
    uint256 public totalDeposits;
    uint256 public maxBorrowRatio = 75;  // 75% LTV max
    
    event Borrowed(address indexed user, uint256 amount, uint256 collateral);
    event Repaid(address indexed user, uint256 amount);
    
    constructor(address _token) { token = IERC20(_token); }
    
    function borrow(uint256 amount, uint256 collateral) external {
        require(collateral > 0, "No collateral");
        uint256 maxBorrow = collateral * maxBorrowRatio / 100;
        require(amount <= maxBorrow, "Exceeds max borrow");  // Fix #108
        require(amount <= totalDeposits, "Insufficient liquidity");
        borrows[msg.sender] += amount;
        token.transfer(msg.sender, amount);
        emit Borrowed(msg.sender, amount, collateral);
    }
    
    function repay(uint256 amount) external {
        require(borrows[msg.sender] >= amount, "Nothing to repay");
        borrows[msg.sender] -= amount;
        token.transferFrom(msg.sender, address(this), amount);
        emit Repaid(msg.sender, amount);
    }
}
