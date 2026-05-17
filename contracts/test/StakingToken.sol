// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @title StakingToken
/// @notice Mock ERC20 token for staking tests with minting capability.
contract StakingToken is ERC20 {
    constructor() ERC20("StakingToken", "STK") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    /// @notice Force-set allowance for testing purposes.
    function forceApprove(address owner, address spender, uint256 amount) external {
        _approve(owner, spender, amount);
    }
}
