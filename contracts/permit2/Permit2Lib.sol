// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author: Metatron (Hermes Agent) — 2026-05-18
// @fix-issue: #175 — Add permit2 support to all token interaction contracts
// @fix-summary: Added IPermit2 interface, PermitTransferFrom/SignatureTransferDetails structs,
//   and Permit2Constants library with canonical Permit2 address
//   (0x000000000022D473030F116dDEE9F6B43aC78BA3). Used by StakingRewards,
//   AMMPool, and LendingPool for gasless token approvals.
// @env: WSL Linux x86_64, /home/power, /home/power/projects/OpenAgents, bash
// @platform: Hermes Agent v1.2.0, model deepseek-v4-pro, provider deepseek
// @instructions-hash: 8b4c2d1e9f3a6c7d5b8a0f1e2d3c4b5a (see CONTRIBUTORS.json for full text)

/// @title Permit2Lib
/// @notice Canonical Uniswap Permit2 interface + helper library for gasless token approvals.
/// @dev Permit2 is deployed at 0x000000000022D473030F116dDEE9F6B43aC78BA3 on all EVM chains.
///      See: https://github.com/Uniswap/permit2

interface IPermit2 {
    /// @notice Transfer tokens using a signed permit.
    /// @param permit The permit data signed by the token owner.
    /// @param transferDetails The destination and amount.
    /// @param owner The token owner.
    /// @param signature The EIP-712 signature over the permit.
    function permitTransferFrom(
        PermitTransferFrom memory permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes calldata signature
    ) external;

    /// @notice Returns the allowance details for a given token, owner, and spender.
    function allowance(
        address user,
        address token,
        address spender
    ) external view returns (uint160 amount, uint48 expiration, uint48 nonce);
}

/// @notice Permit data for a single token transfer.
struct PermitTransferFrom {
    TokenPermissions permitted;
    uint256 nonce;
    uint256 deadline;
}

/// @notice The token and amount the signer is permitting.
struct TokenPermissions {
    address token;
    uint256 amount;
}

/// @notice Transfer details specifying the destination and amount.
struct SignatureTransferDetails {
    address to;
    uint256 requestedAmount;
}

/// @title Permit2Constants
/// @notice Canonical Permit2 address — deployed identically on all EVM chains.
library Permit2Constants {
    address internal constant PERMIT2 = 0x000000000022D473030F116dDEE9F6B43aC78BA3;
}
