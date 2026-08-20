// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";

contract TaskRouter {
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

    // Gas sponsorship state
    mapping(bytes32 => uint256) public agentNonces;
    mapping(bytes32 => uint256) public agentStake;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event SponsoredExecution(bytes32 indexed agentId, address indexed relayer, uint256 gasReimbursed);
    event StakeDeposited(bytes32 indexed agentId, uint256 amount);

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    /// @notice Deposit ETH stake for gas sponsorship reimbursement
    /// @param agentId The agent identifier
    function depositStake(bytes32 agentId) external payable {
        require(msg.value > 0, "Zero stake");
        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.owner == msg.sender, "Not agent owner");
        agentStake[agentId] += msg.value;
        emit StakeDeposited(agentId, msg.value);
    }

    /// @notice Execute a task operation on behalf of an agent with gas sponsorship
    /// @param agentId The agent identifier
    /// @param data The encoded function call to execute
    /// @param nonce The agent's current nonce for replay protection
    /// @param signature ECDSA signature of keccak256(abi.encodePacked(agentId, data, nonce, address(this)))
    function executeOnBehalf(
        bytes32 agentId,
        bytes calldata data,
        uint256 nonce,
        bytes calldata signature
    ) external returns (bool success) {
        // Verify nonce for replay protection
        require(nonce == agentNonces[agentId], "Invalid nonce");

        // Verify agent has sufficient stake for gas reimbursement
        require(agentStake[agentId] > 0, "Insufficient stake");

        // Reconstruct signed message and verify signature
        bytes32 digest = keccak256(abi.encodePacked(agentId, data, nonce, address(this)));
        bytes32 ethSignedHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", digest));
        address signer = ecrecover(ethSignedHash, uint8(signature[64]), bytes32(signature[:32]), bytes32(signature[32:64]));

        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(signer == agent.owner, "Invalid signature");

        // Increment nonce before execution to prevent reentrancy-based replay
        agentNonces[agentId] = nonce + 1;

        // Record gas before execution
        uint256 gasBefore = gasleft();

        // Execute the delegated call
        (success, ) = address(this).call(data);

        // Calculate gas used and reimburse relayer from agent stake
        uint256 gasUsed = gasBefore - gasleft() + 30000; // base overhead
        uint256 gasCost = gasUsed * tx.gasprice;

        require(agentStake[agentId] >= gasCost, "Stake insufficient for gas");
        agentStake[agentId] -= gasCost;

        (bool reimbursed, ) = msg.sender.call{value: gasCost}("");
        require(reimbursed, "Reimbursement failed");

        emit SponsoredExecution(agentId, msg.sender, gasCost);
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

    /// @notice Get current nonce for an agent
    /// @param agentId The agent identifier
    function getAgentNonce(bytes32 agentId) external view returns (uint256) {
        return agentNonces[agentId];
    }

    /// @notice Get staked balance for an agent
    /// @param agentId The agent identifier
    function getAgentStake(bytes32 agentId) external view returns (uint256) {
        return agentStake[agentId];
    }
}
