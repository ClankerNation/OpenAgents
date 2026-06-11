// @generated-by: BountyHunter AI — Coder Agent
// @timestamp: 2026-06-10T01:55:00Z
// @startup-config:
// You are a team member on team "BountyHunter AI".
//
// ## Business Plan
// ### Value Proposition
// **BountyHunter AI** is an automated technical fulfillment engine. We generate income by identifying, solving, and submitting fixes for "bountied" software issues in the open-source ecosystem.
//
// ### Target Customer
// Major tech foundations and VC-backed startups offering financial incentives for bug fixes.
//
// ### Revenue Model
// 100% success-based bounty rewards. Operating 24/7 across hundreds of repositories.
//
// ### The Team
// The Scout, The Architect, The Coder, The Auditor.
//
// ## Working Directory
// Your home directory (`~`) is your private workspace. Clone repositories and work on code here.
//
// ## Shared Directory
// Place files you want to share with the team in `/home/team/shared`.
//
// ## Browser
// agent-browser for web browsing.
//
// ## Exposing Services
// Bind to all interfaces (0.0.0.0). Disable host-header allowlist.
//
// ## Saving Reusable Skills
// Package reusable procedures as skills in /home/team/shared/skills/.
//
// ## Email Inbox
// Email tools available. Send only to verified addresses.
//
// ## Acceptable Use
// Operate honestly. No deceptive or fraudulent activities.
//
// ## LLM Model
// DeepSeek V4 Flash.
//
// ## Team Coordination
// You are The Coder. Teammates: lead, The Architect, The Auditor, The Scout.
// Shared SQLite database via Turso. Use team-db CLI.
//
// ## Available Skills
// team-db, Code Access, agent-browser, find-skills.
//
// ## Sandbox Resources
// Limited memory. Prefer memory-light tooling. Cap build/test concurrency.
// @runtime: Linux x86_64, /home/agent-the-coder/OpenAgents, /tmp/OpenAgents
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title Timelock
/// @notice Time-delayed execution controller for governance actions.
/// @dev Queued transactions must wait a minimum delay before execution.
///      Intended to be the executor behind a GovernorAlpha.
contract Timelock {
    uint256 public constant GRACE_PERIOD = 14 days;
    uint256 public constant MAXIMUM_DELAY = 30 days;
    uint256 public constant MINIMUM_DELAY = 1 hours;  // FIXED: Prevent zero-delay bypass

    address public admin;
    address public pendingAdmin;
    uint256 public delay;

    mapping(bytes32 => bool) public queuedTransactions;

    event NewAdmin(address indexed newAdmin);
    event NewDelay(uint256 indexed newDelay);
    event QueueTransaction(bytes32 indexed txHash, address target, uint256 value, bytes data, uint256 eta);
    event ExecuteTransaction(bytes32 indexed txHash, address target, uint256 value, bytes data, uint256 eta);
    event CancelTransaction(bytes32 indexed txHash, address target, uint256 value, bytes data, uint256 eta);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Timelock: caller is not admin");
        _;
    }

    constructor(address _admin, uint256 _delay) {
        require(_delay <= MAXIMUM_DELAY, "Timelock: delay exceeds max");
        admin = _admin;
        delay = _delay;
    }

    /// @notice Update the execution delay.
    /// @param _delay New delay in seconds.
    /// FIXED: Added onlyAdmin modifier and MINIMUM_DELAY check
    function setDelay(uint256 _delay) external onlyAdmin {
        require(_delay >= MINIMUM_DELAY, "Timelock: delay too low");
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

    /// @notice Set a new pending admin.
    /// @param _pendingAdmin Address of the new pending admin.
    function setPendingAdmin(address _pendingAdmin) external onlyAdmin {
        pendingAdmin = _pendingAdmin;
    }

    /// @notice Queue a transaction for time-delayed execution.
    /// @param target Contract to call.
    /// @param value ETH to send.
    /// @param data Encoded calldata.
    /// @param eta Estimated time of availability (unix timestamp).
    /// FIXED: Added require(eta >= block.timestamp + delay) to prevent eta bypass
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

    /// @notice Cancel a queued transaction.
    function cancelTransaction(
        address target,
        uint256 value,
        bytes calldata data,
        uint256 eta
    ) external onlyAdmin {
        bytes32 txHash = keccak256(abi.encode(target, value, data, eta));
        queuedTransactions[txHash] = false;
        emit CancelTransaction(txHash, target, value, data, eta);
    }

    receive() external payable {}
}