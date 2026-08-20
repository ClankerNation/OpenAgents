// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title Timelock
/// @notice Time-delayed execution controller for governance actions.
/// @dev Queued transactions must wait a minimum delay before execution.
///      Intended to be the executor behind a GovernorAlpha.
contract Timelock {
    uint256 public constant GRACE_PERIOD = 14 days;
    uint256 public constant MINIMUM_DELAY = 1 days;
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
        require(_delay >= MINIMUM_DELAY, "Timelock: delay below min");
        require(_delay <= MAXIMUM_DELAY, "Timelock: delay exceeds max");
        admin = _admin;
        delay = _delay;
    }

    /// @notice Update the execution delay.
    /// @param _delay New delay in seconds.
    function setDelay(uint256 _delay) external onlyAdmin {
        require(_delay >= MINIMUM_DELAY, "Timelock: delay below min");
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
        require(queuedTransactions[txHash], "Timelock: tx not queued");
        queuedTransactions[txHash] = false;
        emit CancelTransaction(txHash, target, value, data, eta);
    }

    receive() external payable {}
}
