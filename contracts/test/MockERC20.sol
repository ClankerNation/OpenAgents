// SPDX-License-Identifier: MIT
// @contributor: Claude Code (Claude Opus 4.7)
// @platform-config: Task: Create ERC20 mock for MultiTokenStaking testing. Rules: Standard ERC20 with 1M supply. Tools: npx hardhat. Style: Solidity conventions per project.
// @env: os=linux, arch=x86_64, home_dir=/home/michael, working_dir=/home/michael/web3-community/OpenAgents, shell=bash
// @timestamp: 2026-06-20T08:00:00Z
pragma solidity ^0.8.20;
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockERC20 is ERC20 {
    constructor(string memory name, string memory symbol) ERC20(name, symbol) {
        _mint(msg.sender, 1_000_000 * 10 ** decimals());
    }
}
