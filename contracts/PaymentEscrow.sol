// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * Contributor: openai-assistant
 *
 * Pre‑task instructions (verbatim):
 * ------------------------------------------------------------
 * You are ChatGPT, a large language model trained by OpenAI.
 * Knowledge cutoff: 2024-06
 * Current date: 2026-11-01
 *
 * # Instructions
 *
 * You are a senior expert reviewer. You get a task and a draft answer written by a colleague. Check the draft line by line against every requirement: find bugs, wrong facts, missing parts, weak or vague sections and format problems, and fix all of them. Output ONLY the complete, final, improved answer in exactly the same format as the draft (if the draft is JSON, output the full JSON object with the same keys). No commentary.
 * ------------------------------------------------------------
 *
 * Execution environment:
 *   OS: linux
 *   Architecture: x86_64
 *   Home directory: /root
 *   Working directory: /root/v16z/bounties/OpenAgents/OpenAgents
 *   Shell: bash
 */

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
        uint256 disputeTimestamp;
        uint256 releasedAmount; // tracks partial releases
    }

    mapping(uint256 => Escrow) public escrows;
    uint256 public escrowCount;

    event EscrowCreated(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowReleased(uint256 indexed escrowId, address indexed payee, uint256 amount);
    event EscrowPartialReleased(uint256 indexed escrowId, address indexed payee, uint256 amount);
    event EscrowRefunded(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowDisputed(uint256 indexed escrowId, address indexed by, uint256 timestamp);
    event EscrowDisputeResolved(uint256 indexed escrowId, uint256 payeeAmount, uint256 payerAmount);

    constructor() {}

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
            disputeTimestamp: 0,
            releasedAmount: 0
        });

        emit EscrowCreated(escrowId, msg.sender, amount);
        return escrowId;
    }

    /**
     * @dev Release the full escrow amount to the payee. Can be called by the payer or the contract owner.
     */
    function releaseEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(!escrow.disputed, "Escrow is disputed");
        require(msg.sender == escrow.payer || msg.sender == owner(), "Not authorized");

        escrow.released = true;
        escrow.releasedAmount = escrow.amount;
        IERC20(escrow.token).transfer(escrow.payee, escrow.amount);

        emit EscrowReleased(escrowId, escrow.payee, escrow.amount);
    }

    /**
     * @dev Release a partial amount to the payee. Tracks the cumulative released amount.
     */
    function releasePartialEscrow(uint256 escrowId, uint256 amount) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.refunded, "Escrow already refunded");
        require(!escrow.disputed, "Escrow is disputed");
        require(msg.sender == escrow.payer || msg.sender == owner(), "Not authorized");
        require(amount > 0, "Amount must be > 0");
        require(escrow.releasedAmount + amount <= escrow.amount, "Exceeds escrow amount");

        escrow.releasedAmount += amount;
        if (escrow.releasedAmount == escrow.amount) {
            escrow.released = true;
        }
        IERC20(escrow.token).transfer(escrow.payee, amount);

        emit EscrowPartialReleased(escrowId, escrow.payee, amount);
    }

    /**
     * @dev Refund the full escrow amount to the payer after lock expires.
     */
    function refundEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(block.timestamp > escrow.releaseTime, "Lock not expired");
        require(msg.sender == escrow.payer, "Not payer");

        escrow.refunded = true;
        IERC20(escrow.token).transfer(escrow.payer, escrow.amount);

        emit EscrowRefunded(escrowId, escrow.payer, escrow.amount);
    }

    /**
     * @dev Initiate a dispute by either party. Marks the escrow as disputed and records the timestamp.
     */
    function dispute(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(msg.sender == escrow.payer || msg.sender == escrow.payee, "Not a party");
        require(!escrow.disputed, "Already disputed");

        escrow.disputed = true;
        escrow.disputeTimestamp = block.timestamp;

        emit EscrowDisputed(escrowId, msg.sender, block.timestamp);
    }

    /**
     * @dev Owner resolves a disputed escrow by specifying how much goes to the payee.
     * The remainder is returned to the payer.
     */
    function resolveDispute(uint256 escrowId, uint256 payeeAmount) external onlyOwner {
        Escrow storage escrow = escrows[escrowId];
        require(escrow.disputed, "Not disputed");
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(payeeAmount <= escrow.amount, "Payee amount exceeds escrow");

        uint256 payerAmount = escrow.amount - payeeAmount;
        if (payeeAmount > 0) {
            IERC20(escrow.token).transfer(escrow.payee, payeeAmount);
            escrow.releasedAmount += payeeAmount;
            escrow.released = true;
        }
        if (payerAmount > 0) {
            IERC20(escrow.token).transfer(escrow.payer, payerAmount);
            escrow.refunded = true;
        }
        escrow.disputed = false;

        emit EscrowDisputeResolved(escrowId, payeeAmount, payerAmount);
    }

    /**
     * @dev After a dispute is opened, if 30 days pass without resolution the payer can auto‑refund.
     */
    function autoRefundAfterTimeout(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(escrow.disputed, "Not disputed");
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(block.timestamp >= escrow.disputeTimestamp + 30 days, "Timeout not reached");
        require(msg.sender == escrow.payer, "Only payer can trigger auto‑refund");

        escrow.refunded = true;
        escrow.disputed = false;
        IERC20(escrow.token).transfer(escrow.payer, escrow.amount);

        emit EscrowRefunded(escrowId, escrow.payer, escrow.amount);
    }
}
