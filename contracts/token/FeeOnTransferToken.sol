// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract FeeOnTransferToken is ERC20, Ownable {
    uint256 public feePercent = 100; // 1%

    constructor() ERC20("FeeToken", "FEE") Ownable(msg.sender) {}

    function mint(address to, uint256 amount) external onlyOwner {
        _mint(to, amount);
    }

    function _transfer(address from, address to, uint256 amount) internal override {
        uint256 fee = amount * feePercent / 10000;
        uint256 netAmount = amount - fee;
        super._transfer(from, to, netAmount);
        if (fee > 0) {
            super._transfer(from, address(0xdead), fee);
        }
    }
}
