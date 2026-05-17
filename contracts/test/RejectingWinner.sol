// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RejectingWinner
/// @notice Test helper: a contract that intentionally rejects ETH transfers.
///         Used to verify PrizeSplit handles contract winners without receive().
/// @dev Has no receive() or fallback() payable function — any ETH transfer will revert.
contract RejectingWinner {
    uint256 public dummy;

    function setDummy(uint256 _val) external {
        dummy = _val;
    }

    /// @notice Attempt to claim prize from PrizeSplit — will revert because
    ///         this contract cannot receive ETH (no receive/fallback).
    function tryClaim(address prizeSplit, uint256 roundId) external {
        // Low-level call to PrizeSplit.claimPrize — PrizeSplit will attempt
        // to send ETH back to this contract, which will revert.
        (bool success, bytes memory data) = prizeSplit.call(
            abi.encodeWithSignature("claimPrize(uint256)", roundId)
        );
        // If PrizeSplit fixes reentrancy correctly, claimed is set BEFORE the
        // external call. But the ETH transfer to us (RejectingWinner) will fail,
        // reverting the entire transaction including the claimed flag update.
        // This is acceptable — the contract winner simply cannot receive ETH,
        // and their prize remains until reclaimed by admin.
        require(success, string(data));
    }
}
