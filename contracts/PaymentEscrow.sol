// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @contributor opencode-gaotax2006
/// @platform You are opencode, an interactive CLI tool...
/// @runtime os=win32 arch=x64 workingdir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
/// @date 2026-05-17T00:00:00Z

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
    }

    mapping(uint256 => Escrow) public escrows;
    uint256 public escrowCount;

    uint256 public constant TIMEOUT_PERIOD = 30 days;

    event EscrowCreated(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowReleased(uint256 indexed escrowId, address indexed payee, uint256 amount);
    event EscrowRefunded(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowDisputed(uint256 indexed escrowId, address indexed initiator);
    event DisputeResolved(uint256 indexed escrowId, address indexed winner, uint256 payerAmount, uint256 payeeAmount);
    event EscrowTimedOut(uint256 indexed escrowId);

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
            disputed: false
        });

        emit EscrowCreated(escrowId, msg.sender, amount);
        return escrowId;
    }

    function releaseEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Under dispute");
        require(msg.sender == escrow.payer || msg.sender == owner(), "Not authorized");

        escrow.released = true;
        IERC20(escrow.token).transfer(escrow.payee, escrow.amount);

        emit EscrowReleased(escrowId, escrow.payee, escrow.amount);
    }

    function refundEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Under dispute");
        require(block.timestamp > escrow.releaseTime, "Lock not expired");
        require(msg.sender == escrow.payer, "Not payer");

        escrow.refunded = true;
        IERC20(escrow.token).transfer(escrow.payer, escrow.amount);

        emit EscrowRefunded(escrowId, escrow.payer, escrow.amount);
    }

    function disputeEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Already disputed");
        require(msg.sender == escrow.payer || msg.sender == escrow.payee, "Not party");

        escrow.disputed = true;
        emit EscrowDisputed(escrowId, msg.sender);
    }

    function resolveDispute(uint256 escrowId, uint256 payerPct) external onlyOwner {
        Escrow storage escrow = escrows[escrowId];
        require(escrow.disputed, "Not disputed");
        require(payerPct <= 100, "Invalid percentage");

        escrow.disputed = false;
        escrow.released = true;

        uint256 payerAmount = (escrow.amount * payerPct) / 100;
        uint256 payeeAmount = escrow.amount - payerAmount;

        if (payerAmount > 0) {
            IERC20(escrow.token).transfer(escrow.payer, payerAmount);
        }
        if (payeeAmount > 0) {
            IERC20(escrow.token).transfer(escrow.payee, payeeAmount);
        }

        emit DisputeResolved(escrowId, address(0), payerAmount, payeeAmount);
    }

    function claimTimeout(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(block.timestamp > escrow.releaseTime + TIMEOUT_PERIOD, "Timeout not reached");

        escrow.refunded = true;
        IERC20(escrow.token).transfer(escrow.payer, escrow.amount);

        emit EscrowTimedOut(escrowId);
    }
}
