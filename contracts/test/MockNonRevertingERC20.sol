// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @notice Mock ERC20 that can be configured to return false on transfer (simulating non-reverting tokens like USDT)
contract MockNonRevertingERC20 is ERC20 {
    bool public shouldFail;

    constructor(string memory name, string memory symbol, uint256 initialSupply) ERC20(name, symbol) {
        _mint(msg.sender, initialSupply);
    }

    function setShouldFail(bool _shouldFail) external {
        shouldFail = _shouldFail;
    }

    /// @dev Returns false instead of reverting when shouldFail is true (mimics USDT/ZRX behavior)
    function transfer(address to, uint256 amount) public override returns (bool) {
        if (shouldFail) {
            return false;
        }
        return super.transfer(to, amount);
    }

    /// @dev Returns false instead of reverting when shouldFail is true
    function transferFrom(address from, address to, uint256 amount) public override returns (bool) {
        if (shouldFail) {
            return false;
        }
        return super.transferFrom(from, to, amount);
    }
}
