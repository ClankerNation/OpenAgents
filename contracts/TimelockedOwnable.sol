// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title TimelockedOwnable — base contract with 2-day timelock on ownership transfer
 * @dev Extends OpenZeppelin Ownable with pending owner + 2-day delay + accept + cancel
 * @contributor Gaotax2006
 * @platform claude-code/opus-4.8
 * @runtime node-v24.15.0 / win32 / amd64
 * @date 2026-06-25
 * @fixes #146 — Adds time-locked ownership transfer to all Ownable contracts
 */
abstract contract TimelockedOwnable is Ownable {
    uint256 public constant TRANSFER_TIMELOCK = 2 days;

    address public pendingOwner;
    uint256 public pendingOwnerTimestamp;

    event OwnershipTransferPending(address indexed newOwner, uint256 availableAt);
    event OwnershipTransferred(address indexed newOwner, uint256 completedAt);
    event OwnershipTransferCancelled();

    /**
     * @notice Initiate ownership transfer — sets pending owner with 2-day timelock.
     * @param newOwner The address proposed to take ownership.
     */
    function transferOwnership(address newOwner) public virtual override onlyOwner {
        require(newOwner != address(0), "TimelockedOwnable: zero address");
        pendingOwner = newOwner;
        pendingOwnerTimestamp = block.timestamp;
        emit OwnershipTransferPending(newOwner, block.timestamp + TRANSFER_TIMELOCK);
    }

    /**
     * @notice Accept ownership transfer — only after timelock has elapsed.
     */
    function acceptOwnership() external virtual {
        require(pendingOwner == msg.sender, "TimelockedOwnable: not pending owner");
        require(block.timestamp >= pendingOwnerTimestamp + TRANSFER_TIMELOCK, "TimelockedOwnable: timelock not elapsed");

        address oldOwner = owner();
        _transferOwnership(msg.sender);
        pendingOwner = address(0);
        pendingOwnerTimestamp = 0;
        emit OwnershipTransferred(msg.sender, block.timestamp);
        emit OwnershipTransferred(oldOwner, block.timestamp);
    }

    /**
     * @notice Cancel pending ownership transfer — only current owner.
     */
    function cancelTransfer() external virtual onlyOwner {
        require(pendingOwner != address(0), "TimelockedOwnable: no pending transfer");
        pendingOwner = address(0);
        pendingOwnerTimestamp = 0;
        emit OwnershipTransferCancelled();
    }
}
