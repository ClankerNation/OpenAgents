// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import "@openzeppelin/contracts/utils/cryptography/SignatureChecker.sol";

/**
 * @title TaskRouter
 * @notice Task routing with gas sponsorship relay for meta-transactions.
 * @contributor Gaotax2006
 * @platform claude-code/opus-4.8
 * @runtime node-v24.15.0 / win32 / amd64
 * @date 2026-06-25
 * @fixes #183 — Add gas sponsorship relay (executeOnBehalf) with signature verification + nonce tracking
 */
contract TaskRouter is EIP712 {
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

    // Nonce tracking per agent for replay protection
    mapping(address => uint256) public agentNonces;

    // EIP712 domain separator is inherited from EIP712

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event SponsoredExecution(uint256 indexed taskId, address indexed agent, address indexed relayer);

    constructor(address _registry, uint256 _platformFee) EIP712("TaskRouter", "1") {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    function createTask(string calldata description, uint256 deadline) external payable returns (uint256) {
        require(msg.value > 0, "Reward required");
        require(deadline > block.timestamp, "Invalid deadline");

        uint256 taskId = taskCount++;
        tasks[taskId] = Task({
            creator: msg.sender,
            assignedAgent: bytes32(0),
            description: description,
            reward: msg.value,
            deadline: deadline,
            status: TaskStatus.Open,
            result: ""
        });

        emit TaskCreated(taskId, msg.sender, msg.value);
        return taskId;
    }

    function assignTask(uint256 taskId, bytes32 agentId) external {
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Open, "Not open");
        require(block.timestamp < task.deadline, "Deadline passed");

        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.active, "Agent not active");
        require(agent.owner == msg.sender, "Not agent owner");

        task.assignedAgent = agentId;
        task.status = TaskStatus.Assigned;

        emit TaskAssigned(taskId, agentId);
    }

    function completeTask(uint256 taskId, bytes calldata result) external {
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Assigned, "Not assigned");

        AgentRegistry.Agent memory agent = registry.getAgent(task.assignedAgent);
        require(agent.owner == msg.sender, "Not assigned agent owner");

        task.result = result;
        task.status = TaskStatus.Completed;

        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;

        (bool success, ) = msg.sender.call{value: payout}("");
        require(success, "Payout failed");

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    function cancelTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.creator == msg.sender, "Not creator");
        require(task.status == TaskStatus.Open, "Cannot cancel");

        task.status = TaskStatus.Cancelled;
        (bool success, ) = msg.sender.call{value: task.reward}("");
        require(success, "Refund failed");
    }

    function disputeTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.creator == msg.sender, "Not creator");
        require(task.status == TaskStatus.Assigned, "Not assigned");
        require(block.timestamp > task.deadline, "Deadline not passed");

        task.status = TaskStatus.Disputed;
        emit TaskDisputed(taskId);
    }

    // ========================
    // Gas Sponsorship Relay
    // ========================

    /**
     * @notice Execute a task on behalf of an agent (meta-transaction / gas sponsorship).
     * @param taskId The task to complete.
     * @param result The task result bytes.
     * @param nonce Agent nonce for replay protection.
     * @param signature Agent's EIP-712 signed authorization.
     * @dev Relayer pays gas; agent must be registered and have approved via signature.
     */
    function executeOnBehalf(
        uint256 taskId,
        bytes calldata result,
        uint256 nonce,
        bytes calldata signature
    ) external {
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Assigned, "Not assigned");

        // Get the agent's owner address from the registry
        AgentRegistry.Agent memory agent = registry.getAgent(task.assignedAgent);
        address agentOwner = agent.owner;

        // Replay protection: check nonce
        require(nonce == agentNonces[agentOwner], "Wrong nonce");
        agentNonces[agentOwner] = nonce + 1;

        // Verify signature
        bytes32 structHash = keccak256(
            abi.encode(
                EXECUTION_TYPEHASH,
                taskId,
                keccak256(result),
                nonce,
                address(this)
            )
        );

        bytes32 hash = hashTypedDataV4(structHash);
        require(
            SignatureChecker.isValidSignatureNow(agentOwner, hash, signature),
            "Invalid signature"
        );

        // Mark execution
        task.result = result;
        task.status = TaskStatus.Completed;

        // Pay platform fee to deployer
        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;

        // Transfer reward to agent owner (relayer paid gas upfront)
        require(address(this).balance >= payout, "Insufficient contract balance");
        (bool success, ) = agentOwner.call{value: payout}("");
        require(success, "Payout failed");

        emit TaskCompleted(taskId, task.assignedAgent);
        emit SponsoredExecution(taskId, agentOwner, msg.sender);
    }

    // EIP-712 typehash for executeOnBehalf
    bytes32 public constant EXECUTION_TYPEHASH = keccak256(
        "ExecuteOnBehalf(uint256 taskId,bytes result,uint256 nonce,address contractAddress)"
    );

    /**
     * @notice Get current nonce for an agent (used by relayers to construct signatures).
     */
    function getAgentNonce(address agentOwner) external view returns (uint256) {
        return agentNonces[agentOwner];
    }
}
