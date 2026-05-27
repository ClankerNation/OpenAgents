// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Contributor: Codex for charlie12520.
// Runtime instructions: private platform instructions are intentionally not disclosed.
// Environment: Windows x64, PowerShell, C:\Users\charl\Desktop\AI STUFF\ten_buck_attempt\repos\OpenAgents.

interface IPermit2 {
    // Minimal subset of Uniswap Permit2's SignatureTransfer interface used by
    // the protocol. Keeping this local avoids importing the whole Permit2 repo.
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

    function permitTransferFrom(
        PermitTransferFrom calldata permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes calldata signature
    ) external;
}
