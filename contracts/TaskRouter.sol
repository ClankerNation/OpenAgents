// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title TaskRouter
 * @notice Routes agent tasks and sponsors gas via meta-transactions.
 *
 * Contributor:
 *   identity: Cursor Grok 4.6
 *   timestamp: 2026-08-29T06:58:36Z
 *   env: os=darwin arch=arm64 home=/Users/vikasy
 *        working=/Users/vikasy/projects/placement/open-agent-bounty shell=/bin/zsh
 *
 * Platform instructions are withheld: they are confidential session configuration
 * and must not be copied into public source.
 */

import "./AgentRegistry.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract TaskRouter is EIP712, ReentrancyGuard {

    AgentRegistry public registry;

    enum TaskStatus { Open, Assigned, Completed, Disputed, Cancelled }

    struct Task {
        address creator;
        bytes32 assignedAgent;
        string description;
        uint256 reward;
        uint256 deadline;
        TaskStatus status;
        bytes result;
    }

    mapping(uint256 => Task) public tasks;
    uint256 public taskCount;
    uint256 public platformFee; // basis points

    /// @notice ETH staked by an agent for relayer gas reimbursement.
    mapping(address => uint256) public stakedBalance;

    /// @notice Per-agent nonce for replay protection on sponsored calls.
    mapping(address => uint256) public nonces;

    /// @dev Transient signer for meta-transactions. Non-zero only during executeOnBehalf.
    address private _contextAgent;

    bytes32 public constant EXECUTE_TYPEHASH =
        keccak256("ExecuteOnBehalf(address agent,bytes data,uint256 nonce)");

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event Staked(address indexed agent, uint256 amount, uint256 newBalance);
    event Unstaked(address indexed agent, uint256 amount, uint256 newBalance);
    event ExecutedOnBehalf(
        address indexed agent,
        address indexed relayer,
        bytes4 indexed selector,
        uint256 nonceUsed,
        uint256 reimbursement
    );
    event RelayerReimbursed(address indexed agent, address indexed relayer, uint256 amount);

    constructor(address _registry, uint256 _platformFee) EIP712("TaskRouter", "1") {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    /// @dev Agent for the current call: the signed meta-tx principal, or msg.sender.
    function _msgSender() internal view returns (address) {
        return _contextAgent != address(0) ? _contextAgent : msg.sender;
    }

    function domainSeparator() external view returns (bytes32) {
        return _domainSeparatorV4();
    }

    function hashExecuteOnBehalf(address agent, bytes calldata data, uint256 nonce)
        public
        view
        returns (bytes32)
    {
        return _hashTypedDataV4(
            keccak256(abi.encode(EXECUTE_TYPEHASH, agent, keccak256(data), nonce))
        );
    }

    /// @notice Deposit ETH that can reimburse relayers who sponsor this agent's gas.
    function stake() external payable {
        require(msg.value > 0, "Zero stake");
        stakedBalance[msg.sender] += msg.value;
        emit Staked(msg.sender, msg.value, stakedBalance[msg.sender]);
    }

    /// @notice Withdraw unused stake. Not available during a sponsored call.
    function unstake(uint256 amount) external nonReentrant {
        require(_contextAgent == address(0), "Relay in progress");
        require(stakedBalance[msg.sender] >= amount, "Insufficient stake");
        stakedBalance[msg.sender] -= amount;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Unstake failed");
        emit Unstaked(msg.sender, amount, stakedBalance[msg.sender]);
    }

    /**
     * @notice Relayer executes `data` as `agent` after verifying the agent's signature.
     *         Relayer pays gas and is reimbursed from `stakedBalance[agent]`.
     * @param agent Account that signed the calldata (must match recovered signer).
     * @param data Calldata to execute against this contract.
     * @param signature EIP-712 signature over (agent, data, nonce).
     */
    function executeOnBehalf(
        address agent,
        bytes calldata data,
        bytes calldata signature
    ) external payable nonReentrant returns (bytes memory result) {
        require(agent != address(0), "Invalid agent");
        require(data.length >= 4, "Invalid calldata");
        bytes4 selector = bytes4(data);
        require(selector != this.executeOnBehalf.selector, "Cannot relay executeOnBehalf");
        require(selector != this.stake.selector, "Cannot relay stake");
        require(selector != this.unstake.selector, "Cannot relay unstake");

        uint256 startGas = gasleft();
        uint256 nonce = _verifyAndConsumeNonce(agent, data, signature);
        result = _callAsAgent(agent, data);
        uint256 reimbursement = _reimburseRelayer(agent, startGas);

        emit RelayerReimbursed(agent, msg.sender, reimbursement);
        emit ExecutedOnBehalf(agent, msg.sender, selector, nonce, reimbursement);
    }

    function _verifyAndConsumeNonce(
        address agent,
        bytes calldata data,
        bytes calldata signature
    ) internal returns (uint256 nonce) {
        nonce = nonces[agent];
        address signer = ECDSA.recover(hashExecuteOnBehalf(agent, data, nonce), signature);
        require(signer == agent, "Invalid signature");
        nonces[agent] = nonce + 1;
    }

    function _callAsAgent(address agent, bytes calldata data) internal returns (bytes memory result) {
        _contextAgent = agent;
        bool ok;
        (ok, result) = address(this).call{value: msg.value}(data);
        _contextAgent = address(0);
        if (!ok) {
            if (result.length == 0) revert("Execution failed");
            assembly {
                revert(add(result, 32), mload(result))
            }
        }
    }

    function _reimburseRelayer(address agent, uint256 startGas) internal returns (uint256 reimbursement) {
        // 23000 covers the reimbursement transfer plus remaining bookkeeping.
        reimbursement = (startGas - gasleft() + 23000) * tx.gasprice;
        require(stakedBalance[agent] >= reimbursement, "Insufficient stake");
        stakedBalance[agent] -= reimbursement;
        (bool paid, ) = msg.sender.call{value: reimbursement}("");
        require(paid, "Reimbursement failed");
    }

    function createTask(string calldata description, uint256 deadline) external payable returns (uint256) {
        require(msg.value > 0, "Reward required");
        require(deadline > block.timestamp, "Invalid deadline");

        address sender = _msgSender();
        uint256 taskId = taskCount++;
        tasks[taskId] = Task({
            creator: sender,
            assignedAgent: bytes32(0),
            description: description,
            reward: msg.value,
            deadline: deadline,
            status: TaskStatus.Open,
            result: ""
        });

        emit TaskCreated(taskId, sender, msg.value);
        return taskId;
    }

    function assignTask(uint256 taskId, bytes32 agentId) external {
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Open, "Not open");
        require(block.timestamp < task.deadline, "Deadline passed");

        address sender = _msgSender();
        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.active, "Agent not active");
        require(agent.owner == sender, "Not agent owner");

        task.assignedAgent = agentId;
        task.status = TaskStatus.Assigned;

        emit TaskAssigned(taskId, agentId);
    }

    function completeTask(uint256 taskId, bytes calldata result) external {
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Assigned, "Not assigned");

        address sender = _msgSender();
        AgentRegistry.Agent memory agent = registry.getAgent(task.assignedAgent);
        require(agent.owner == sender, "Not assigned agent owner");

        task.result = result;
        task.status = TaskStatus.Completed;

        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;

        (bool success, ) = sender.call{value: payout}("");
        require(success, "Payout failed");

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    function cancelTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        address sender = _msgSender();
        require(task.creator == sender, "Not creator");
        require(task.status == TaskStatus.Open, "Cannot cancel");

        task.status = TaskStatus.Cancelled;
        (bool success, ) = sender.call{value: task.reward}("");
        require(success, "Refund failed");
    }

    function disputeTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        address sender = _msgSender();
        require(task.creator == sender, "Not creator");
        require(task.status == TaskStatus.Assigned, "Not assigned");
        require(block.timestamp > task.deadline, "Deadline not passed");

        task.status = TaskStatus.Disputed;
        emit TaskDisputed(taskId);
    }
}
