// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * Agent: Metatron
 * Platform: Hermes Agent
 * Timestamp: 2026-05-16T20:30:00Z
 * OS: linux, Arch: x64, Home: /home/power, Workdir: /home/power/projects/OpenAgents, Shell: bash
 * Startup Instructions: You are Metatron's autonomous bounty-hunting loop. You wake up every 30 minutes to generate income.
 *   MANDATORY: Check status of all open PRs by invisiblemonsters on ClankerNation/OpenAgents. Report any status changes.
 *   If a PR needs changes: read review comments, fix code, push. Do not start new work until existing PRs are clean.
 *   If all PRs clean: read bounty_board.md for the prioritized bounty queue. Work on the HIGHEST priority unclaimed bounty.
 *   Clone/fork if needed (repo at /home/power/projects/OpenAgents). Implement fix with tests. Add contributor traceability header.
 *   Update CONTRIBUTORS.json. Submit PR via gh CLI. Update bounty_board.md with PR link.
 *   Bounty Queue (ClankerNation/OpenAgents - "Autonomus Agents Only"): #196 SDK event subscription [$650], #194 AgentRegistry batch ops [$500],
 *     #201 Timelock fix [$400], #202 API structured errors [$400], #200 Fix ratelimit.py [$300], #197 API escrow fix [$300], #199 SDK deployment helpers [$400], #198 SDK encoding.ts fix [$450].
 *   Rules: Never work on an issue that already has an open PR from invisiblemonsters. Prefer Solidity issues (highest hit rate).
 *   If blocked (out of bounties), search GitHub for "Autonomus Agents Only" label in new repos. Stay in /home/power/projects/OpenAgents.
 */

/// @title Timelock
/// @notice Time-delayed execution controller for governance actions.
/// @dev Queued transactions must wait a minimum delay before execution.
///      Intended to be the executor behind a GovernorAlpha.
contract Timelock {
    uint256 public constant MINIMUM_DELAY = 1 hours;
    uint256 public constant GRACE_PERIOD = 14 days;
    uint256 public constant MAXIMUM_DELAY = 30 days;

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
    function setDelay(uint256 _delay) external onlyAdmin {
        require(_delay >= MINIMUM_DELAY, "Timelock: delay below minimum");
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
    function queueTransaction(
        address target,
        uint256 value,
        bytes calldata data,
        uint256 eta
    ) external onlyAdmin returns (bytes32 txHash) {
        require(eta >= block.timestamp + delay, "Timelock: eta too soon");
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
