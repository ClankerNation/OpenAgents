// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract PaymentEscrow {
    address public owner;
    mapping(address => uint256) public escrows;

    constructor() {
        owner = msg.sender;
    }

    function createEscrow(address token, address contributor, uint256 amount) external {
        require(amount > 0, "Amount must be greater than zero");
        IERC20(token).transferFrom(msg.sender, address(this), amount);
        escrows[contributor] += amount;
    }

    function withdraw(address token, address recipient, uint256 amount) external {
        require(escrows[msg.sender] >= amount, "Insufficient funds in escrow");
        IERC20(token).transfer(recipient, amount);
        escrows[msg.sender] -= amount;
    }
}