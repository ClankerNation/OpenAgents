// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockNonRevertingERC20 is ERC20 {
    bool public shouldFail;

    constructor() ERC20("MockToken", "MCK") {
        _mint(msg.sender, 1000000 * 10**18);
    }

    function setShouldFail(bool _fail) external {
        shouldFail = _fail;
    }

    function transfer(address to, uint256 amount) public override returns (bool) {
        if (shouldFail) {
            return false; // Non-reverting failure
        }
        return super.transfer(to, amount);
    }

    function transferFrom(address from, address to, uint256 amount) public override returns (bool) {
        if (shouldFail) {
            return false;
        }
        return super.transferFrom(from, to, amount);
    }
}
