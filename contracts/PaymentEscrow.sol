// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract PaymentEscrow {
    IERC20 public token;
    mapping(address => uint256) public balances;
    
    event Deposited(address indexed user, uint256 amount);
    event Released(address indexed from, address indexed to, uint256 amount);
    
    constructor(address _token) { token = IERC20(_token); }
    
    function deposit(uint256 amount) external {
        require(amount > 0, "Zero amount not allowed");  // Fix #179
        token.transferFrom(msg.sender, address(this), amount);
        balances[msg.sender] += amount;
        emit Deposited(msg.sender, amount);
    }
    
    function release(address to, uint256 amount) external {
        require(amount > 0, "Zero amount not allowed");  // Fix #179
        require(balances[msg.sender] >= amount, "Insufficient balance");
        balances[msg.sender] -= amount;
        token.transfer(to, amount);
        emit Released(msg.sender, to, amount);
    }
}
