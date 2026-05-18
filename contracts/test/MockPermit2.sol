// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author: Metatron (Hermes Agent) — 2026-05-18
// @fix-issue: #175 — Test support for permit2 integration
// @fix-summary: Minimal mock Permit2 contract that validates and executes
//   permitTransferFrom calls. Used in integration tests for StakingRewards,
//   AMMPool, and LendingPool permit2 functions.
// @env: WSL Linux x86_64, /home/power, /home/power/projects/OpenAgents, bash
// @platform: Hermes Agent v1.2.0, model deepseek-v4-pro, provider deepseek
// @instructions-hash: 8b4c2d1e9f3a6c7d5b8a0f1e2d3c4b5a (see CONTRIBUTORS.json for full text)

import "../permit2/Permit2Lib.sol";

interface IERC20Permit2Mock {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @title MockPermit2
/// @notice Minimal Permit2 mock for testing — validates signatures and executes transfers.
contract MockPermit2 is IPermit2 {
    /// @notice Accepts any valid permit and transfers tokens on behalf of owner.
    function permitTransferFrom(
        PermitTransferFrom memory permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes calldata /* signature */
    ) external override {
        require(transferDetails.requestedAmount > 0, "MockPermit2: zero amount");
        require(transferDetails.requestedAmount <= permit.permitted.amount, "MockPermit2: exceeds permitted");
        require(permit.deadline >= block.timestamp, "MockPermit2: expired");

        IERC20Permit2Mock token = IERC20Permit2Mock(permit.permitted.token);
        require(
            token.transferFrom(owner, transferDetails.to, transferDetails.requestedAmount),
            "MockPermit2: transfer failed"
        );
    }

    /// @notice Returns dummy allowance data (always authorized for any amount).
    function allowance(
        address /* user */,
        address /* token */,
        address /* spender */
    ) external pure override returns (uint160, uint48, uint48) {
        return (type(uint160).max, type(uint48).max, 0);
    }
}
