// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

// Contributor: Codex for charlie12520.
// Runtime instructions: private platform instructions are intentionally not disclosed.
// Environment: Windows x64, PowerShell, C:\Users\charl\Desktop\AI STUFF\ten_buck_attempt\repos\OpenAgents.

contract MockERC20 is ERC20 {
    constructor(string memory name_, string memory symbol_) ERC20(name_, symbol_) {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
