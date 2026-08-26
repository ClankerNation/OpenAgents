// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract StakingToken is ERC20 {
    constructor() ERC20("Staking Token", "STK") {}
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

contract RewardToken is ERC20 {
    constructor() ERC20("Reward Token", "RWD") {}
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
