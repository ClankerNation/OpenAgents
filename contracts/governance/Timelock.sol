// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @custom:contributor-info
///   author: EVM0x
///   github: https://github.com/EVM0x
///   timestamp: 2026-07-07T07:20:00+08:00
///   os: Linux (6.8.0-117-generic)
///   arch: x86_64
///   home: /home/ubuntu
///   workdir: /home/ubuntu/openagents-fix
///   shell: /bin/bash
///
/// @title Timelock
/// @notice Time-delayed execution controller for governance actions.
/// @dev Queued transactions must wait a minimum delay before execution
///      and expire after a grace period. Intended to be the executor
///      behind a GovernorAlpha.
contract Timelock {
    uint256 public constant GRACE_PERIOD = 14 days;
    uint256 public constant MAXIMUM_DELAY = 30 days;
    uint256 public constant MINIMUM_DELAY = 1 days;

    address public admin;
    address public pendingAdmin;
    uint256 public delay;

    mapping(bytes32 => bool) public queuedTransactions;

    event NewAdmin(address indexed newAdmin);
    event NewPendingAdmin(address indexed pendingAdmin);
    event NewDelay(uint256 indexed oldDelay, uint256 indexed newDelay);
    event QueueTransaction(bytes32 indexed txHash, address indexed target, uint256 value, bytes data, uint256 eta);
    event ExecuteTransaction(bytes32 indexed txHash, address indexed target, uint256 value, bytes data, uint256 eta);
    event CancelTransaction(bytes32 indexed txHash, address indexed target, uint256 value, bytes data, uint256 eta);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Timelock: caller is not admin");
        _;
    }

    /// @param _admin Initial admin address.
    /// @param _delay Initial execution delay in seconds.
    constructor(address _admin, uint256 _delay) {
        require(_delay >= MINIMUM_DELAY, "Timelock: delay below min");
        require(_delay <= MAXIMUM_DELAY, "Timelock: delay exceeds max");
        admin = _admin;
        delay = _delay;
    }

    /// @notice Update the execution delay. Only callable by admin.
    /// @param _delay New delay in seconds. Must be between MINIMUM_DELAY and MAXIMUM_DELAY.
    function setDelay(uint256 _delay) external onlyAdmin {
        require(_delay >= MINIMUM_DELAY, "Timelock: delay below min");
        require(_delay <= MAXIMUM_DELAY, "Timelock: delay exceeds max");
        uint256 oldDelay = delay;
        delay = _delay;
        emit NewDelay(oldDelay, _delay);
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
        require(_pendingAdmin != address(0), "Timelock: zero address");
        pendingAdmin = _pendingAdmin;
        emit NewPendingAdmin(_pendingAdmin);
    }

    /// @notice Queue a transaction for time-delayed execution.
    /// @dev Enforces eta >= block.timestamp + delay to prevent immediate execution.
    /// @param target Contract to call.
    /// @param value ETH to send.
    /// @param data Encoded calldata.
    /// @param eta Estimated time of availability (unix timestamp).
    /// @return txHash Unique transaction identifier.
    function queueTransaction(
        address target,
        uint256 value,
        bytes calldata data,
        uint256 eta
    ) external onlyAdmin returns (bytes32 txHash) {
        require(eta >= block.timestamp + delay, "Timelock: eta too soon");
        txHash = keccak256(abi.encode(target, value, data, eta));
        require(!queuedTransactions[txHash], "Timelock: tx already queued");
        queuedTransactions[txHash] = true;
        emit QueueTransaction(txHash, target, value, data, eta);
    }

    /// @notice Execute a previously queued transaction.
    /// @dev Reverts if eta hasn't been reached or has expired past the grace period.
    /// @param target Contract to call.
    /// @param value ETH to send.
    /// @param data Encoded calldata.
    /// @param eta Estimated time of availability (unix timestamp).
    /// @return result Return data from the executed call.
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

    /// @notice Cancel a queued transaction. Only callable by admin.
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
