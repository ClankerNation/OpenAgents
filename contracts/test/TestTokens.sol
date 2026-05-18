// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @notice Minimal ERC20 mock with mint() for testing.
contract StakingToken is ERC20 {
    constructor() ERC20("Staking Token", "STK") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

/// @notice Alias for test compatibility.
contract RewardToken is ERC20 {
    constructor() ERC20("Reward Token", "RWD") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
