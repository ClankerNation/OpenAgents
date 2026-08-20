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
        uint256 releaseTime;
        bool released;
        bool refunded;
        bool disputed;
        uint256 disputeTime;
    }

    mapping(uint256 => Escrow) public escrows;
    uint256 public escrowCount;

    uint256 public constant DISPUTE_TIMEOUT = 30 days;

    event EscrowCreated(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowReleased(uint256 indexed escrowId, address indexed payee, uint256 amount);
    event EscrowRefunded(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowDisputed(uint256 indexed escrowId, address indexed disputer);
    event DisputeResolved(uint256 indexed escrowId, uint256 payerAmount, uint256 payeeAmount);

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
            releaseTime: block.timestamp + lockDuration,
            released: false,
            refunded: false,
            disputed: false,
            disputeTime: 0
        });

        emit EscrowCreated(escrowId, msg.sender, amount);
        return escrowId;
    }

    function releaseEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Escrow disputed");
        require(msg.sender == escrow.payer || msg.sender == owner(), "Not authorized");

        escrow.released = true;
        IERC20(escrow.token).transfer(escrow.payee, escrow.amount);

        emit EscrowReleased(escrowId, escrow.payee, escrow.amount);
    }

    function refundEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Escrow disputed");
        require(block.timestamp > escrow.releaseTime, "Lock not expired");
        require(msg.sender == escrow.payer, "Not payer");

        escrow.refunded = true;
        IERC20(escrow.token).transfer(escrow.payer, escrow.amount);

        emit EscrowRefunded(escrowId, escrow.payer, escrow.amount);
    }

    /// @notice Either party can dispute the escrow to prevent automatic settlement.
    function disputeEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Already disputed");
        require(msg.sender == escrow.payer || msg.sender == escrow.payee, "Not party");

        escrow.disputed = true;
        escrow.disputeTime = block.timestamp;

        emit EscrowDisputed(escrowId, msg.sender);
    }

    /// @notice Owner resolves a dispute by splitting funds between payer and payee.
    /// @param payerAmount Amount returned to payer; remainder goes to payee.
    function resolveDispute(uint256 escrowId, uint256 payerAmount) external onlyOwner {
        Escrow storage escrow = escrows[escrowId];
        require(escrow.disputed, "Not disputed");
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(payerAmount <= escrow.amount, "Exceeds escrow");

        uint256 payeeAmount = escrow.amount - payerAmount;
        escrow.released = true; // Mark as settled to prevent further actions

        if (payerAmount > 0) {
            IERC20(escrow.token).transfer(escrow.payer, payerAmount);
        }
        if (payeeAmount > 0) {
            IERC20(escrow.token).transfer(escrow.payee, payeeAmount);
        }

        emit DisputeResolved(escrowId, payerAmount, payeeAmount);
    }

    /// @notice Auto-refund after dispute timeout if unresolved.
    function timeoutRefund(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(escrow.disputed, "Not disputed");
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(block.timestamp >= escrow.disputeTime + DISPUTE_TIMEOUT, "Timeout not reached");

        escrow.refunded = true;
        IERC20(escrow.token).transfer(escrow.payer, escrow.amount);

        emit EscrowRefunded(escrowId, escrow.payer, escrow.amount);
    }

    /// @notice Partial release of escrow funds to payee.
    function partialRelease(uint256 escrowId, uint256 amount) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Escrow disputed");
        require(msg.sender == escrow.payer || msg.sender == owner(), "Not authorized");
        require(amount > 0 && amount <= escrow.amount, "Invalid amount");

        escrow.amount -= amount;
        IERC20(escrow.token).transfer(escrow.payee, amount);

        emit EscrowReleased(escrowId, escrow.payee, amount);
    }
}
