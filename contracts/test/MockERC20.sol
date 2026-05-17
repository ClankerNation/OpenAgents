// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @title MockERC20
/// @notice Minimal mock ERC20 token with free mint for testing.
contract MockERC20 is ERC20 {
    constructor(string memory name, string memory symbol) ERC20(name, symbol) {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    /// @dev Exposed for test convenience — allows StakingRewards tests (ethers v5)
    ///      that call .deployed() to work. Not used in ethers v6.
    function deployed() external pure returns (bool) {
        return true;
    }
}
