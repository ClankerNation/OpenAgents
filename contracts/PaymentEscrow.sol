// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor oocheol
 * @platform Gemini CLI engineering agent. Focus: Non-destructive, idiomatic code modifications, comprehensive testing, and secure credential handling. Follows Research-Strategy-Execution lifecycle.
 * @runtime os=win32, arch=x64, home_dir=C:\Users\PC, working_directory=C:\chromeMCP\OpenAgents, shell=powershell
 * @date 2026-05-19T05:15:00Z
 *
 * PaymentEscrow with dispute resolution, partial release, and automated timeout refunds.
 */

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract PaymentEscrow is Ownable {
    struct Escrow {
        address payer;
        address payee;
        address token;
        uint256 totalAmount;
        uint256 releasedAmount;
        uint256 releaseTime;
        bool settled;
        bool disputed;
    }

    mapping(uint256 => Escrow) public escrows;
    uint256 public escrowCount;

    uint256 public constant TIMEOUT_PERIOD = 30 days;

    event EscrowCreated(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowReleased(uint256 indexed escrowId, address indexed payee, uint256 amount);
    event EscrowRefunded(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowDisputed(uint256 indexed escrowId, address indexed initiator);
    event DisputeResolved(uint256 indexed escrowId, uint256 payerAmount, uint256 payeeAmount);
    event EscrowPartialRelease(uint256 indexed escrowId, uint256 amount);

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
            totalAmount: amount,
            releasedAmount: 0,
            releaseTime: block.timestamp + lockDuration,
            settled: false,
            disputed: false
        });

        emit EscrowCreated(escrowId, msg.sender, amount);
        return escrowId;
    }

    function partialRelease(uint256 escrowId, uint256 amount) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.settled, "Already settled");
        require(!escrow.disputed, "Under dispute");
        require(msg.sender == escrow.payer, "Not payer");
        
        uint256 remaining = escrow.totalAmount - escrow.releasedAmount;
        require(amount > 0 && amount <= remaining, "Invalid amount");

        escrow.releasedAmount += amount;
        if (escrow.releasedAmount == escrow.totalAmount) {
            escrow.settled = true;
        }

        IERC20(escrow.token).transfer(escrow.payee, amount);
        emit EscrowPartialRelease(escrowId, amount);
    }

    function releaseEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.settled, "Already settled");
        require(!escrow.disputed, "Under dispute");
        require(msg.sender == escrow.payer || msg.sender == owner(), "Not authorized");

        uint256 amountToRelease = escrow.totalAmount - escrow.releasedAmount;
        escrow.releasedAmount = escrow.totalAmount;
        escrow.settled = true;

        IERC20(escrow.token).transfer(escrow.payee, amountToRelease);
        emit EscrowReleased(escrowId, escrow.payee, amountToRelease);
    }

    function refundEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.settled, "Already settled");
        require(!escrow.disputed, "Under dispute");
        require(block.timestamp > escrow.releaseTime, "Lock not expired");
        require(msg.sender == escrow.payer, "Not payer");

        uint256 amountToRefund = escrow.totalAmount - escrow.releasedAmount;
        escrow.settled = true;

        IERC20(escrow.token).transfer(escrow.payer, amountToRefund);
        emit EscrowRefunded(escrowId, escrow.payer, amountToRefund);
    }

    function disputeEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.settled, "Already settled");
        require(!escrow.disputed, "Already disputed");
        require(msg.sender == escrow.payer || msg.sender == escrow.payee, "Not party");

        escrow.disputed = true;
        emit EscrowDisputed(escrowId, msg.sender);
    }

    function resolveDispute(uint256 escrowId, uint256 payerPct) external onlyOwner {
        Escrow storage escrow = escrows[escrowId];
        require(escrow.disputed, "Not disputed");
        require(payerPct <= 100, "Invalid percentage");

        uint256 remaining = escrow.totalAmount - escrow.releasedAmount;
        uint256 payerAmount = (remaining * payerPct) / 100;
        uint256 payeeAmount = remaining - payerAmount;

        escrow.disputed = false;
        escrow.settled = true;
        escrow.releasedAmount = escrow.totalAmount;

        if (payerAmount > 0) {
            IERC20(escrow.token).transfer(escrow.payer, payerAmount);
        }
        if (payeeAmount > 0) {
            IERC20(escrow.token).transfer(escrow.payee, payeeAmount);
        }

        emit DisputeResolved(escrowId, payerAmount, payeeAmount);
    }

    function autoRefund(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.settled, "Already settled");
        require(!escrow.disputed, "Under dispute");
        require(block.timestamp > escrow.releaseTime + TIMEOUT_PERIOD, "Timeout not reached");

        uint256 amountToRefund = escrow.totalAmount - escrow.releasedAmount;
        escrow.settled = true;

        IERC20(escrow.token).transfer(escrow.payer, amountToRefund);
        emit EscrowRefunded(escrowId, escrow.payer, amountToRefund);
    }
}
