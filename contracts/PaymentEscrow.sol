// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract PaymentEscrow {
    mapping(address => uint256) public balances;
    
    event PaymentMade(address indexed payer, uint256 amount);
    event Withdrawn(address indexed payee, uint256 amount);
    
    function deposit() external payable {
        require(msg.value > 0, "PaymentEscrow: zero amount not allowed");
        balances[msg.sender] += msg.value;
        emit PaymentMade(msg.sender, msg.value);
    }
    
    function withdraw(uint256 amount) external {
        require(amount > 0, "PaymentEscrow: zero amount not allowed");
        require(balances[msg.sender] >= amount, "PaymentEscrow: insufficient balance");
        balances[msg.sender] -= amount;
        payable(msg.sender).transfer(amount);
        emit Withdrawn(msg.sender, amount);
    }
}