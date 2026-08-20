// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract PaymentEscrow is Ownable {
    struct Escrow {
        address payer;
        address payee;
        address token;
        uint256 amount;
        uint256 remainingAmount;
        uint256 releaseTime;
        bool released;
        bool refunded;
        bool disputed;
    }

    mapping(uint256 => Escrow) public escrows;
    uint256 public escrowCount;

    event EscrowCreated(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowReleased(uint256 indexed escrowId, address indexed payee, uint256 amount);
    event EscrowRefunded(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowDisputed(uint256 indexed escrowId, address indexed disputer);
    event DisputeResolved(uint256 indexed escrowId, uint256 payerShare, uint256 payeeShare);
    event PartialRelease(uint256 indexed escrowId, uint256 amount);

    constructor() Ownable(msg.sender) {}

    function createEscrow(
        address payee,
        address token,
        uint256 amount,
        uint256 lockDuration
    ) external returns (uint256) {
        require(payee != address(0), "Invalid payee");
        require(amount > 0, "Amount must be > 0");

        IERC20(token).transferFrom(msg.sender, address(this), amount);

        uint256 escrowId = escrowCount++;
        escrows[escrowId] = Escrow({
            payer: msg.sender,
            payee: payee,
            token: token,
            amount: amount,
            remainingAmount: amount,
            releaseTime: block.timestamp + lockDuration,
            released: false,
            refunded: false,
            disputed: false
        });

        emit EscrowCreated(escrowId, msg.sender, amount);
        return escrowId;
    }

    function releaseEscrow(uint256 escrowId) external {
        releasePartial(escrowId, escrows[escrowId].remainingAmount);
    }

    /// @notice Release a portion of the escrow to the payee.
    /// @param escrowId The escrow to release from.
    /// @param amount Amount to release (must be <= remainingAmount).
    function releasePartial(uint256 escrowId, uint256 amount) public {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.disputed, "Escrow disputed — resolve first");
        require(!escrow.refunded, "Already refunded");
        require(amount > 0 && amount <= escrow.remainingAmount, "Invalid amount");
        require(msg.sender == escrow.payer || msg.sender == owner(), "Not authorized");

        escrow.remainingAmount -= amount;
        if (escrow.remainingAmount == 0) {
            escrow.released = true;
        }
        IERC20(escrow.token).transfer(escrow.payee, amount);

        emit PartialRelease(escrowId, amount);
        if (escrow.released) {
            emit EscrowReleased(escrowId, escrow.payee, amount);
        }
    }

    function refundEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Escrow disputed — resolve first");
        require(block.timestamp > escrow.releaseTime, "Lock not expired");
        require(msg.sender == escrow.payer, "Not payer");

        uint256 refundAmount = escrow.remainingAmount;
        escrow.remainingAmount = 0;
        escrow.refunded = true;
        IERC20(escrow.token).transfer(escrow.payer, refundAmount);

        emit EscrowRefunded(escrowId, escrow.payer, refundAmount);
    }

    /// @notice Dispute an escrow. Either party can dispute before settlement.
    /// @param escrowId The escrow to dispute.
    function dispute(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Already disputed");
        require(msg.sender == escrow.payer || msg.sender == escrow.payee, "Not party to escrow");

        escrow.disputed = true;
        emit EscrowDisputed(escrowId, msg.sender);
    }

    /// @notice Resolve a disputed escrow. Owner splits remaining funds between parties.
    /// @param escrowId The disputed escrow to resolve.
    /// @param payerShare Amount to return to payer (remainder goes to payee).
    function resolveDispute(uint256 escrowId, uint256 payerShare) external onlyOwner {
        Escrow storage escrow = escrows[escrowId];
        require(escrow.disputed, "Not disputed");
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(payerShare <= escrow.remainingAmount, "Exceeds remaining");

        uint256 payeeShare = escrow.remainingAmount - payerShare;
        escrow.remainingAmount = 0;
        escrow.disputed = false;
        escrow.released = true; // Mark as settled

        if (payerShare > 0) {
            IERC20(escrow.token).transfer(escrow.payer, payerShare);
        }
        if (payeeShare > 0) {
            IERC20(escrow.token).transfer(escrow.payee, payeeShare);
        }

        emit DisputeResolved(escrowId, payerShare, payeeShare);
    }
}
