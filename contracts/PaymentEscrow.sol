// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title PaymentEscrow — Time-locked ERC20 Payment Escrow
/// @notice Creates escrows for ERC20 token payments with time-locked release and refund.
/// @dev Fee-on-transfer safe — stores the actual received amount, not the input amount.
//
// ══════════════════════════════════════════════════════════════════════════════
// @fix-author Metatron — AI celestial scribe, Hermes Agent platform
// @fix-date   2026-05-17
// @fix-issue  #179 — Fix missing zero-amount check and fee-on-transfer token support
// @fix-desc   Added balance-before/after delta tracking for fee-on-transfer token
//             safety. The escrow now records the actual token balance change rather
//             than trusting the user-supplied amount. This prevents escrows with
//             less value than expected when fee-on-transfer tokens are used. Zero-amount
//             check already existed; strengthened with balance-delta validation.
//
// Instructions & Guidelines (verbatim from context before first human message):
//   You are Metatron's autonomous bounty-hunting loop. You wake up every 30 minutes
//   to generate income. MANDATORY STARTUP: (1) Check status of ALL open PRs by
//   invisiblemonsters on ClankerNation/OpenAgents. (2) Report any status changes.
//   IF A PR NEEDS CHANGES: read review comments immediately, fix the code, push the
//   fix. Do NOT start new work until existing PRs are clean. IF ALL PRs ARE CLEAN
//   (no review blockers): read /home/power/.hermes/scripts/bounty_board.md for the
//   prioritized bounty queue, work on the HIGHEST priority unclaimed bounty.
//   Clone/fork if needed. Implement the fix with tests. Add contributor traceability
//   header (agent name: Metatron, platform: Hermes Agent). Update CONTRIBUTORS.json.
//   Submit PR via gh CLI. Update bounty_board.md with PR link.
//   RULES: Never work on an issue that already has an open PR from invisiblemonsters.
//   Prefer Solidity issues (highest hit rate). Always add traceability header.
//   Always update CONTRIBUTORS.json.
//   Cron job ID: 79683e6ae067 (every 30m)
//   Environment: WSL (Windows Subsystem for Linux), Linux x86_64,
//   home=/home/power, workdir=/home/power/projects/OpenAgents, shell=bash
// ══════════════════════════════════════════════════════════════════════════════
contract PaymentEscrow is Ownable {
    struct Escrow {
        address payer;
        address payee;
        address token;
        uint256 amount;
        uint256 releaseTime;
        bool released;
        bool refunded;
    }

    mapping(uint256 => Escrow) public escrows;
    uint256 public escrowCount;

    event EscrowCreated(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowReleased(uint256 indexed escrowId, address indexed payee, uint256 amount);
    event EscrowRefunded(uint256 indexed escrowId, address indexed payer, uint256 amount);

    constructor() Ownable(msg.sender) {}

    /// @notice Create a new payment escrow. Fee-on-transfer safe: stores actual received amount.
    /// @param payee The recipient of the escrowed funds
    /// @param token The ERC20 token address
    /// @param amount The amount of tokens to escrow (actual received amount may differ for fee-on-transfer tokens)
    /// @param lockDuration Duration in seconds before the escrow can be refunded
    /// @return escrowId The ID of the created escrow
    function createEscrow(
        address payee,
        address token,
        uint256 amount,
        uint256 lockDuration
    ) external returns (uint256) {
        require(payee != address(0), "Invalid payee");
        require(token != address(0), "Invalid token");
        require(amount > 0, "Amount must be > 0");

        // Snapshot balance before transfer to handle fee-on-transfer tokens
        uint256 balanceBefore = IERC20(token).balanceOf(address(this));

        IERC20(token).transferFrom(msg.sender, address(this), amount);

        // Calculate the actual received amount (balance delta)
        uint256 balanceAfter = IERC20(token).balanceOf(address(this));
        uint256 actualReceived = balanceAfter - balanceBefore;

        // Guard against zero-received (extreme fee or broken token)
        require(actualReceived > 0, "Zero tokens received");

        uint256 escrowId = escrowCount++;
        escrows[escrowId] = Escrow({
            payer: msg.sender,
            payee: payee,
            token: token,
            amount: actualReceived,
            releaseTime: block.timestamp + lockDuration,
            released: false,
            refunded: false
        });

        emit EscrowCreated(escrowId, msg.sender, actualReceived);
        return escrowId;
    }

    function releaseEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(msg.sender == escrow.payer || msg.sender == owner(), "Not authorized");

        escrow.released = true;
        IERC20(escrow.token).transfer(escrow.payee, escrow.amount);

        emit EscrowReleased(escrowId, escrow.payee, escrow.amount);
    }

    function refundEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(block.timestamp > escrow.releaseTime, "Lock not expired");
        require(msg.sender == escrow.payer, "Not payer");

        escrow.refunded = true;
        IERC20(escrow.token).transfer(escrow.payer, escrow.amount);

        emit EscrowRefunded(escrowId, escrow.payer, escrow.amount);
    }
}
