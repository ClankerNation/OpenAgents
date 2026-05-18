// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title NoReceiveContract
/// @notice A contract with no receive() or fallback() — rejects all ETH transfers
contract NoReceiveContract {
    // Intentionally no receive() or fallback()
    // Any ETH transfer to this contract will revert
}
