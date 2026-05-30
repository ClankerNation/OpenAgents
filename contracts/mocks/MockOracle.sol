/**
 * @fix-author: Antigravity
 * @date: 2026-05-30
 * @runtime:
 *   os: mac
 *   arch: arm64
 *   working_dir: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents
 *   shell: /bin/zsh
 * 
 * Verbatim Startup Context:
 * You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding.
 * You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
 * The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is.
 * This information may or may not be relevant to the coding task, it is up for you to decide.
 */

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MockOracle {
    mapping(address => uint256) public prices;

    function setPrice(address token, uint256 price) external {
        prices[token] = price;
    }

    function getPrice(address token) external view returns (uint256) {
        uint256 price = prices[token];
        require(price > 0, "MockOracle: price not set");
        return price;
    }
}
