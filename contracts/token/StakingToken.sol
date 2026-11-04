// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @notice Plain ERC20 used as the stakeable asset in tests and local deployments.
contract StakingToken is ERC20 {
    constructor() ERC20("Staking Token", "STK") {
        _mint(msg.sender, 1_000_000 ether);
    }

    /// @notice Open mint, for tests and local deployments.
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
