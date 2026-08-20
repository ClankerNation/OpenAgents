// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author rafaio1
// @date 2026-08-20
// @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
// @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

/// @title TimelockedOwnable
/// @notice Ownership transfer with a mandatory timelock delay to prevent instant admin compromise.
/// @dev Replaces OpenZeppelin Ownable with a 2-day pending owner pattern.
abstract contract TimelockedOwnable {
    address private _owner;
    address private _pendingOwner;
    uint256 private _transferInitiatedAt;

    /// @dev Minimum delay between initiating and accepting ownership transfer (2 days)
    uint256 public constant OWNERSHIP_TRANSFER_DELAY = 2 days;

    event OwnershipTransferStarted(address indexed previousOwner, address indexed newOwner, uint256 availableAt);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event OwnershipTransferCancelled(address indexed previousOwner, address indexed cancelledPending);

    modifier onlyOwner() {
        require(msg.sender == _owner, "TimelockedOwnable: not owner");
        _;
    }

    constructor() {
        _owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);
    }

    function owner() public view returns (address) {
        return _owner;
    }

    function pendingOwner() public view returns (address) {
        return _pendingOwner;
    }

    function ownershipTransferAvailableAt() public view returns (uint256) {
        if (_pendingOwner == address(0)) return 0;
        return _transferInitiatedAt + OWNERSHIP_TRANSFER_DELAY;
    }

    /// @notice Initiate ownership transfer to a new address. Subject to timelock.
    /// @param newOwner Address of the proposed new owner.
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "TimelockedOwnable: zero address");
        require(newOwner != _owner, "TimelockedOwnable: already owner");
        _pendingOwner = newOwner;
        _transferInitiatedAt = block.timestamp;
        emit OwnershipTransferStarted(_owner, newOwner, block.timestamp + OWNERSHIP_TRANSFER_DELAY);
    }

    /// @notice Accept ownership after the timelock delay has passed. Only callable by pending owner.
    function acceptOwnership() external {
        require(msg.sender == _pendingOwner, "TimelockedOwnable: not pending owner");
        require(block.timestamp >= _transferInitiatedAt + OWNERSHIP_TRANSFER_DELAY, "TimelockedOwnable: delay not elapsed");
        address oldOwner = _owner;
        _owner = _pendingOwner;
        _pendingOwner = address(0);
        _transferInitiatedAt = 0;
        emit OwnershipTransferred(oldOwner, _owner);
    }

    /// @notice Cancel a pending ownership transfer. Only callable by current owner.
    function cancelOwnershipTransfer() external onlyOwner {
        require(_pendingOwner != address(0), "TimelockedOwnable: no pending transfer");
        address cancelled = _pendingOwner;
        _pendingOwner = address(0);
        _transferInitiatedAt = 0;
        emit OwnershipTransferCancelled(_owner, cancelled);
    }
}
