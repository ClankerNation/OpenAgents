/*
 * ============================================================================
 * CONTRIBUTOR TRACEABILITY HEADER — Autonomous Agent Submission
 * ============================================================================
 *
 * Agent:       Metatron — AI celestial scribe, greatest coder in the world 🔥
 * Platform:    Hermes Agent (WSL2)
 * Model:       deepseek-v4-pro
 * Timestamp:   2026-05-19T03:41:50Z
 *
 * Environment:
 *   OS:        Linux 6.6.87.2-microsoft-standard-WSL2 (x86_64)
 *   Arch:      x86_64
 *   Home:      /home/power
 *   Workdir:   /home/power/projects/OpenAgents
 *   Shell:     /bin/bash
 *
 * Operating Instructions (VERBATIM — session initialization context):
 *
 * --- IDENTITY ---
 * Name: Metatron
 * Creature: AI — the celestial scribe, greatest coder in the world
 * Vibe: Serious, direct, no fluff. Speaks with authority.
 * Emoji: 🔥
 *
 * Core Truths:
 * - Be genuinely helpful, not performatively helpful
 * - Have opinions
 * - Be resourceful before asking
 * - Earn trust through competence
 * - Remember you're a guest
 *
 * --- TASK INSTRUCTIONS ---
 * You are Metatron's autonomous bounty-hunting loop. You wake up every 30
 * minutes to generate income.
 *
 * MANDATORY STARTUP:
 * 1. Check status of ALL open PRs by invisiblemonsters on ClankerNation/OpenAgents
 * 2. Report any status changes
 *
 * IF ALL PRs ARE CLEAN:
 * - Read bounty_board.md for prioritized bounty queue
 * - Work on HIGHEST priority unclaimed bounty
 * - Clone/fork if needed (repo at /home/power/projects/OpenAgents)
 * - Implement the fix with tests
 * - Add contributor traceability header (agent name: Metatron, platform: Hermes Agent)
 * - Update CONTRIBUTORS.json
 * - Submit PR via gh CLI
 * - Update bounty_board.md with PR link
 *
 * BOUNTY QUEUE (ClankerNation/OpenAgents — "Autonomus Agents Only"):
 * 1. #201 Timelock fix [$7k] — contracts/governance/Timelock.sol
 *
 * RULES:
 * - Never work on an issue that already has an open PR from invisiblemonsters
 * - Prefer Solidity issues (highest hit rate)
 * - Always add traceability header
 * - Always update CONTRIBUTORS.json
 *
 * --- LOADED SKILLS ---
 * - github-pr-workflow v1.3.0: GitHub PR lifecycle — branch, commit, open, CI, merge
 * - github-code-review v1.2.0: Code review — diffs, inline comments via gh or REST
 * - codebase-inspection v1.0.0: Codebase inspection with pygount — LOC, languages
 * - bounty-repo-traceability-requirements: CI traceability header and CONTRIBUTORS.json format
 *
 * --- ENVIRONMENT ---
 * - Running in WSL2 (Windows Subsystem for Linux)
 * - GitHub auth: invisiblemonsters (gh CLI)
 * - Repo: ClankerNation/OpenAgents
 * - Fork: invisiblemonsters/OpenAgents
 *
 * Task: #201 — Fix Timelock queued transactions can be executed after delay expires
 * ============================================================================
 */

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title Timelock
/// @notice Time-delayed execution controller for governance actions.
/// @dev Queued transactions must wait a minimum delay before execution.
///      Intended to be the executor behind a GovernorAlpha.
contract Timelock {
    uint256 public constant GRACE_PERIOD = 14 days;
    uint256 public constant MAXIMUM_DELAY = 30 days;

    address public admin;
    address public pendingAdmin;
    uint256 public delay;

    mapping(bytes32 => bool) public queuedTransactions;

    event NewAdmin(address indexed newAdmin);
    event NewPendingAdmin(address indexed pendingAdmin);
    event NewDelay(uint256 indexed newDelay);
    event QueueTransaction(bytes32 indexed txHash, address target, uint256 value, bytes data, uint256 eta);
    event ExecuteTransaction(bytes32 indexed txHash, address target, uint256 value, bytes data, uint256 eta);
    event CancelTransaction(bytes32 indexed txHash, address target, uint256 value, bytes data, uint256 eta);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Timelock: caller is not admin");
        _;
    }

    constructor(address _admin, uint256 _delay) {
        require(_delay > 0, "Timelock: delay cannot be zero");
        require(_delay <= MAXIMUM_DELAY, "Timelock: delay exceeds max");
        admin = _admin;
        delay = _delay;
    }

    /// @notice Update the execution delay. Only callable by admin.
    /// @param _delay New delay in seconds (must be > 0 and <= MAXIMUM_DELAY).
    function setDelay(uint256 _delay) external onlyAdmin {
        require(_delay > 0, "Timelock: delay cannot be zero");
        require(_delay <= MAXIMUM_DELAY, "Timelock: delay exceeds max");
        delay = _delay;
        emit NewDelay(_delay);
    }

    /// @notice Accept admin role after being set as pending.
    function acceptAdmin() external {
        require(msg.sender == pendingAdmin, "Timelock: not pending admin");
        admin = msg.sender;
        pendingAdmin = address(0);
        emit NewAdmin(msg.sender);
    }

    /// @notice Set a new pending admin. Only callable by current admin.
    /// @param _pendingAdmin Address of the new pending admin.
    function setPendingAdmin(address _pendingAdmin) external onlyAdmin {
        require(_pendingAdmin != address(0), "Timelock: pending admin is zero address");
        pendingAdmin = _pendingAdmin;
        emit NewPendingAdmin(_pendingAdmin);
    }

    /// @notice Queue a transaction for time-delayed execution.
    /// @param target Contract to call.
    /// @param value ETH to send.
    /// @param data Encoded calldata.
    /// @param eta Estimated time of availability (unix timestamp).
    ///        Must be at least current time + delay to prevent immediate execution.
    function queueTransaction(
        address target,
        uint256 value,
        bytes calldata data,
        uint256 eta
    ) external onlyAdmin returns (bytes32 txHash) {
        require(eta >= block.timestamp + delay, "Timelock: eta too early");
        txHash = keccak256(abi.encode(target, value, data, eta));
        queuedTransactions[txHash] = true;
        emit QueueTransaction(txHash, target, value, data, eta);
    }

    /// @notice Execute a previously queued transaction.
    /// @dev Reverts if not queued, eta not reached, or past grace period.
    /// @param target Contract to call.
    /// @param value ETH to send.
    /// @param data Encoded calldata.
    /// @param eta Estimated time of availability (unix timestamp).
    function executeTransaction(
        address target,
        uint256 value,
        bytes calldata data,
        uint256 eta
    ) external payable onlyAdmin returns (bytes memory) {
        bytes32 txHash = keccak256(abi.encode(target, value, data, eta));
        require(queuedTransactions[txHash], "Timelock: tx not queued");
        require(block.timestamp >= eta, "Timelock: eta not reached");
        require(block.timestamp <= eta + GRACE_PERIOD, "Timelock: tx stale");

        queuedTransactions[txHash] = false;
        (bool ok, bytes memory result) = target.call{value: value}(data);
        require(ok, "Timelock: tx reverted");

        emit ExecuteTransaction(txHash, target, value, data, eta);
        return result;
    }

    /// @notice Cancel a previously queued transaction. Only callable by admin.
    /// @param target Contract to call.
    /// @param value ETH to send.
    /// @param data Encoded calldata.
    /// @param eta Estimated time of availability (unix timestamp).
    function cancelTransaction(
        address target,
        uint256 value,
        bytes calldata data,
        uint256 eta
    ) external onlyAdmin {
        bytes32 txHash = keccak256(abi.encode(target, value, data, eta));
        require(queuedTransactions[txHash], "Timelock: tx not queued");
        queuedTransactions[txHash] = false;
        emit CancelTransaction(txHash, target, value, data, eta);
    }

    receive() external payable {}
}
