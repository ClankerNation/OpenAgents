// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockERC20 is ERC20 {
    constructor(string memory name_, string memory symbol_) ERC20(name_, symbol_) {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

contract FeeOnTransferToken is ERC20 {
    uint256 public feePercent;

    constructor(string memory name_, string memory symbol_, uint256 _feePercent) ERC20(name_, symbol_) {
        feePercent = _feePercent;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    function transferFrom(address from, address to, uint256 amount) public override returns (bool) {
        uint256 fee = (amount * feePercent) / 100;
        uint256 netAmount = amount - fee;
        _transfer(from, to, netAmount);
        _approve(from, msg.sender, allowance(from, msg.sender) - amount);
        return true;
    }
}
