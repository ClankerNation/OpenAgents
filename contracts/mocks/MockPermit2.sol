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

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

struct TokenPermissions {
    address token;
    uint256 amount;
}

struct PermitTransferFrom {
    TokenPermissions permitted;
    uint256 nonce;
    uint256 deadline;
}

struct SignatureTransferDetails {
    address to;
    uint256 requestedAmount;
}

contract MockPermit2 {
    event PermitTransfer(address indexed token, address indexed from, address indexed to, uint256 amount);

    function permitTransferFrom(
        PermitTransferFrom calldata permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes calldata /* signature */
    ) external {
        require(permit.permitted.token != address(0), "Invalid token");
        require(transferDetails.requestedAmount <= permit.permitted.amount, "Amount exceeds permitted");
        
        IERC20(permit.permitted.token).transferFrom(owner, transferDetails.to, transferDetails.requestedAmount);
        emit PermitTransfer(permit.permitted.token, owner, transferDetails.to, transferDetails.requestedAmount);
    }
}
