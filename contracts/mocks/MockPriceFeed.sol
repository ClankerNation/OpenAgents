// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Contributor: Codex for charlie12520.
// Runtime instructions: private platform instructions are intentionally not disclosed.
// Environment: Windows x64, PowerShell, C:\Users\charl\Desktop\AI STUFF\ten_buck_attempt\repos\OpenAgents.

contract MockPriceFeed {
    mapping(address => uint256) public prices;

    function setPrice(address token, uint256 price) external {
        prices[token] = price;
    }

    function getPrice(address token) external view returns (uint256) {
        return prices[token];
    }
}
