// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @title RewardToken
/// @notice Mock ERC20 token for reward distribution tests with minting capability.
contract RewardToken is ERC20 {
    constructor() ERC20("RewardToken", "RWD") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
