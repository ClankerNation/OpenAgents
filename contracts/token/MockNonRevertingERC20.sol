// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockNonRevertingERC20 is ERC20 {
    bool public failNextTransfer;

    constructor() ERC20("MockToken", "MTK") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    function setFailNextTransfer(bool fail) external {
        failNextTransfer = fail;
    }

    function transfer(address to, uint256 amount) public virtual override returns (bool) {
        if (failNextTransfer) {
            failNextTransfer = false; // Reset after one failure
            return false;
        }
        return super.transfer(to, amount);
    }

    function transferFrom(address from, address to, uint256 amount) public virtual override returns (bool) {
        if (failNextTransfer) {
            failNextTransfer = false;
            return false;
        }
        return super.transferFrom(from, to, amount);
    }
}
