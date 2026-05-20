// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract PaymentEscrow is Ownable {
    using SafeERC20 for IERC20;

    struct Escrow {
        address payer;
        address payee;
        address token;
        uint256 amount;
        uint256 releasedAmount;
        uint256 refundedAmount;
        uint256 releaseTime;
        bool released;
        bool refunded;
        bool disputed;
    }

    mapping(uint256 => Escrow) public escrows;
    uint256 public escrowCount;
    uint256 public constant AUTO_REFUND_DELAY = 30 days;

    event EscrowCreated(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowReleased(uint256 indexed escrowId, address indexed payee, uint256 amount);
    event EscrowRefunded(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowDisputed(uint256 indexed escrowId, address indexed initiator);
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
            releasedAmount: 0,
            refundedAmount: 0,
            releaseTime: block.timestamp + lockDuration,
            released: false,
            refunded: false,
            disputed: false
        });

        emit EscrowCreated(escrowId, msg.sender, amount);
        return escrowId;
    }

    function releaseEscrow(uint256 escrowId) external {
        _releaseEscrow(escrowId, remainingAmount(escrowId));
    }

    function releaseEscrow(uint256 escrowId, uint256 amount) external {
        _releaseEscrow(escrowId, amount);
    }

    function _releaseEscrow(uint256 escrowId, uint256 amount) internal {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Under dispute");
        require(msg.sender == escrow.payer || msg.sender == owner(), "Not authorized");
        require(amount > 0 && amount <= remainingAmount(escrowId), "Invalid release amount");

        escrow.releasedAmount += amount;
        if (remainingAmount(escrowId) == 0) {
            escrow.released = true;
        }
        IERC20(escrow.token).safeTransfer(escrow.payee, amount);

        emit EscrowReleased(escrowId, escrow.payee, amount);
    }

    function refundEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Under dispute");
        require(block.timestamp > escrow.releaseTime, "Lock not expired");
        require(msg.sender == escrow.payer, "Not payer");

        uint256 amount = remainingAmount(escrowId);
        escrow.refunded = true;
        escrow.refundedAmount += amount;
        IERC20(escrow.token).safeTransfer(escrow.payer, amount);

        emit EscrowRefunded(escrowId, escrow.payer, amount);
    }

    function dispute(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Already disputed");
        require(msg.sender == escrow.payer || msg.sender == escrow.payee, "Not party");

        escrow.disputed = true;
        emit EscrowDisputed(escrowId, msg.sender);
    }

    function resolveDispute(uint256 escrowId, uint256 payerAmount, uint256 payeeAmount) external onlyOwner {
        Escrow storage escrow = escrows[escrowId];
        require(escrow.disputed, "Not disputed");
        uint256 remaining = remainingAmount(escrowId);
        require(payerAmount + payeeAmount == remaining, "Invalid split");

        escrow.disputed = false;
        escrow.released = true;
        escrow.refunded = true;
        escrow.refundedAmount += payerAmount;
        escrow.releasedAmount += payeeAmount;

        if (payerAmount > 0) {
            IERC20(escrow.token).safeTransfer(escrow.payer, payerAmount);
        }
        if (payeeAmount > 0) {
            IERC20(escrow.token).safeTransfer(escrow.payee, payeeAmount);
        }

        emit DisputeResolved(escrowId, payerAmount, payeeAmount);
    }

    function refundExpiredEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(block.timestamp > escrow.releaseTime + AUTO_REFUND_DELAY, "Timeout not reached");

        uint256 amount = remainingAmount(escrowId);
        escrow.refunded = true;
        escrow.refundedAmount += amount;
        IERC20(escrow.token).safeTransfer(escrow.payer, amount);

        emit EscrowRefunded(escrowId, escrow.payer, amount);
    }

    function remainingAmount(uint256 escrowId) public view returns (uint256) {
        Escrow storage escrow = escrows[escrowId];
        return escrow.amount - escrow.releasedAmount - escrow.refundedAmount;
    }
}
