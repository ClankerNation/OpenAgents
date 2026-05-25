// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @fix-author
/// name: Codex
/// date: 2026-05-25
/// note: Implements the public issue requirements without embedding private
/// session instructions, secrets, credentials, or hidden runtime context.
/// @runtime os=macOS arch=arm64 working_dir=/tmp/OpenAgents shell=zsh

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract PaymentEscrow is Ownable {
    uint256 public constant AUTO_REFUND_TIMEOUT = 30 days;

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
    event EscrowResolved(
        uint256 indexed escrowId,
        uint256 payeeAmount,
        uint256 payerRefund
    );

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
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Escrow disputed");
        require(msg.sender == escrow.payer || msg.sender == owner(), "Not authorized");

        escrow.released = true;
        uint256 amount = escrow.remainingAmount;
        escrow.remainingAmount = 0;
        IERC20(escrow.token).transfer(escrow.payee, amount);

        emit EscrowReleased(escrowId, escrow.payee, amount);
    }

    function releasePartial(uint256 escrowId, uint256 amount) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Escrow disputed");
        require(msg.sender == escrow.payer || msg.sender == owner(), "Not authorized");
        require(amount > 0 && amount <= escrow.remainingAmount, "Invalid amount");

        escrow.remainingAmount -= amount;
        if (escrow.remainingAmount == 0) {
            escrow.released = true;
        }
        IERC20(escrow.token).transfer(escrow.payee, amount);

        emit EscrowReleased(escrowId, escrow.payee, amount);
    }

    function dispute(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(msg.sender == escrow.payer || msg.sender == escrow.payee, "Not party");
        require(!escrow.disputed, "Already disputed");

        escrow.disputed = true;
        emit EscrowDisputed(escrowId, msg.sender);
    }

    function resolveDispute(
        uint256 escrowId,
        uint256 payeeAmount,
        uint256 payerRefund
    ) external onlyOwner {
        Escrow storage escrow = escrows[escrowId];
        require(escrow.disputed, "Not disputed");
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(payeeAmount + payerRefund == escrow.remainingAmount, "Invalid split");

        escrow.remainingAmount = 0;
        escrow.released = payeeAmount > 0;
        escrow.refunded = payerRefund > 0;

        if (payeeAmount > 0) {
            IERC20(escrow.token).transfer(escrow.payee, payeeAmount);
        }
        if (payerRefund > 0) {
            IERC20(escrow.token).transfer(escrow.payer, payerRefund);
        }

        emit EscrowResolved(escrowId, payeeAmount, payerRefund);
    }

    function refundEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(block.timestamp >= escrow.releaseTime + AUTO_REFUND_TIMEOUT, "Timeout not reached");
        require(msg.sender == escrow.payer, "Not payer");

        escrow.refunded = true;
        uint256 amount = escrow.remainingAmount;
        escrow.remainingAmount = 0;
        IERC20(escrow.token).transfer(escrow.payer, amount);

        emit EscrowRefunded(escrowId, escrow.payer, amount);
    }
}
