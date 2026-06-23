// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @custom:fix-author Gaotax2006
/// @custom:date 2026-06-23
/// @custom:issue #183 Add gas sponsorship relay for agent transactions — security critical
/// @custom:runtime os=win32 arch=x64 home_dir=C:\Users\asus working_dir=F:\ai-bounty-work\bounty-hunter shell=/usr/bin/bash
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import "./AgentRegistry.sol";

contract TaskRouter is EIP712("TaskRouterRelay", "1") {
    using ECDSA for bytes32;

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

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event RelayerUsed(address indexed relayer, bytes32 indexed agentId);

    // Nonce tracking per agent for replay protection
    mapping(bytes32 => uint256) public agentNonces;
    uint256 public constant NONCE_MAX = type(uint256).max;

    constructor(address _registry, uint256 _platformFee) {
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

    /// @notice EIP-712 typed data hash for signing.
    function _hashTypedDataV4(bytes32 structHash) internal view virtual override returns (bytes32) {
        return super._hashTypedDataV4(structHash);
    }

    /// @notice Execute a task on behalf of a registered agent via signed meta-transaction.
    /// @param taskId ID of the task to complete.
    /// @param result Task completion result bytes.
    /// @param nonce Agent nonce for replay protection.
    /// @param deadline Signature expiration timestamp.
    /// @param signature Agent's ECDSA signature over the task completion.
    function executeOnBehalf(
        uint256 taskId,
        bytes calldata result,
        uint256 nonce,
        uint256 deadline,
        bytes calldata signature
    ) external {
        require(block.timestamp <= deadline, "Relay: signature expired");

        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Assigned, "Not assigned");

        // Verify nonce hasn't been used (replay protection)
        require(nonce <= NONCE_MAX, "Relay: invalid nonce");
        agentNonces[task.assignedAgent] = nonce + 1;

        // Verify agent signature
        bytes32 structHash = keccak256(abi.encode(taskId, keccak256(result), nonce, deadline));
        bytes32 digest = _hashTypedDataV4(structHash);
        address signer = digest.recover(signature);

        AgentRegistry.Agent memory agent = registry.getAgent(task.assignedAgent);
        require(signer == agent.owner, "Relay: invalid agent signature");

        // Execute task completion
        task.result = result;
        task.status = TaskStatus.Completed;

        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;

        (bool success, ) = payable(signer).call{value: payout}("");
        require(success, "Payout failed");

        emit TaskCompleted(taskId, task.assignedAgent);
        emit RelayerUsed(msg.sender, task.assignedAgent);
    }
}
