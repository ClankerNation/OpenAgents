// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author rafaio1
// @date 2026-08-20
// @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
// @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

import "@openzeppelin/contracts/access/Ownable.sol";

/// @title TimelockOwnable
/// @notice Extends OZ Ownable with a 2-day timelock on ownership transfers
abstract contract TimelockOwnable is Ownable {
    address private _pendingOwner;
    uint256 private _transferInitiatedAt;

    uint256 public constant TIMELOCK_DELAY = 2 days;

    event OwnershipTransferInitiated(address indexed previousOwner, address indexed newOwner, uint256 executeAfter);
    event OwnershipTransferCancelled(address indexed previousOwner, address indexed cancelledNewOwner);
    event OwnershipAccepted(address indexed previousOwner, address indexed newOwner);

    constructor() Ownable(msg.sender) {}

    /// @notice Initiates a timed ownership transfer (replaces instant transferOwnership)
    function transferOwnership(address newOwner) public override onlyOwner {
        require(newOwner != address(0), "New owner is zero");
        require(newOwner != owner(), "Already owner");
        _pendingOwner = newOwner;
        _transferInitiatedAt = block.timestamp;
        emit OwnershipTransferInitiated(owner(), newOwner, block.timestamp + TIMELOCK_DELAY);
    }

    /// @notice Pending owner accepts after timelock expires
    function acceptOwnership() external {
        require(msg.sender == _pendingOwner, "Not pending owner");
        require(_transferInitiatedAt > 0, "No pending transfer");
        require(block.timestamp >= _transferInitiatedAt + TIMELOCK_DELAY, "Timelock not expired");

        address oldOwner = owner();
        _transferOwnership(msg.sender);
        _pendingOwner = address(0);
        _transferInitiatedAt = 0;
        emit OwnershipAccepted(oldOwner, msg.sender);
    }

    /// @notice Current owner cancels a pending transfer
    function cancelTransfer() external onlyOwner {
        require(_pendingOwner != address(0), "No pending transfer");
        address cancelled = _pendingOwner;
        _pendingOwner = address(0);
        _transferInitiatedAt = 0;
        emit OwnershipTransferCancelled(owner(), cancelled);
    }

    function pendingOwner() external view returns (address) {
        return _pendingOwner;
    }

    function transferInitiatedAt() external view returns (uint256) {
        return _transferInitiatedAt;
    }
}
