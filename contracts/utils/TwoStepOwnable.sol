// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

/// @contributor opencode-gaotax2006
/// @platform You are opencode, an interactive CLI tool...
/// @runtime os=win32 arch=x64 workingdir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
/// @date 2026-05-17T00:00:00Z

abstract contract TwoStepOwnable is Ownable {
    uint256 public constant OWNER_TRANSFER_DELAY = 2 days;

    address public pendingOwner;
    uint256 public pendingOwnerSetTime;

    event OwnershipTransferStarted(address indexed currentOwner, address indexed pendingOwner);
    event OwnershipTransferCanceled(address indexed currentOwner);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    constructor(address initialOwner) Ownable(initialOwner) {}

    function transferOwnership(address newOwner) public override onlyOwner {
        require(newOwner != address(0), "Zero address");
        pendingOwner = newOwner;
        pendingOwnerSetTime = block.timestamp;
        emit OwnershipTransferStarted(owner(), newOwner);
    }

    function acceptOwnership() external {
        require(msg.sender == pendingOwner, "Not pending owner");
        require(block.timestamp >= pendingOwnerSetTime + OWNER_TRANSFER_DELAY, "Delay not met");
        address previousOwner = owner();
        _transferOwnership(pendingOwner);
        delete pendingOwner;
        delete pendingOwnerSetTime;
        emit OwnershipTransferred(previousOwner, msg.sender);
    }

    function cancelOwnershipTransfer() external onlyOwner {
        require(pendingOwner != address(0), "No pending transfer");
        delete pendingOwner;
        delete pendingOwnerSetTime;
        emit OwnershipTransferCanceled(msg.sender);
    }

    function renounceOwnership() public override onlyOwner {
        require(pendingOwner == address(0), "Pending transfer active");
        super.renounceOwnership();
    }
}
