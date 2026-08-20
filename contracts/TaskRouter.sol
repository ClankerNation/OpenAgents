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

    // Gas sponsorship relay state
    mapping(bytes32 => uint256) public agentNonces;
    mapping(address => uint256) public agentStakes;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event SponsoredExecution(bytes32 indexed agentId, address indexed relayer, uint256 gasReimbursement);

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    /// @notice Deposit stake for gas sponsorship reimbursement.
    function depositStake() external payable {
        require(msg.value > 0, "Zero stake");
        agentStakes[msg.sender] += msg.value;
    }

    /// @notice Execute a transaction on behalf of an agent (meta-transaction).
    /// @param agentId The agent's identifier.
    /// @param data The calldata to execute.
    /// @param nonce Replay protection nonce.
    /// @param signature ECDSA signature from the agent owner over keccak256(agentId, data, nonce).
    function executeOnBehalf(
        bytes32 agentId,
        bytes calldata data,
        uint256 nonce,
        bytes calldata signature
    ) external returns (bool success, bytes memory returnData) {
        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.active, "Agent not active");

        // Verify nonce for replay protection
        require(agentNonces[agentId] == nonce, "Invalid nonce");

        // Reconstruct signed hash and verify agent owner signature
        bytes32 digest = keccak256(abi.encodePacked(agentId, data, nonce));
        bytes32 ethSignedHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", digest));
        address signer = ecrecover(ethSignedHash, uint8(signature[64]), bytes32(signature[:32]), bytes32(signature[32:64]));
        require(signer == agent.owner, "Invalid signature");

        // Check sufficient stake for gas reimbursement estimate
        uint256 gasBefore = gasleft();
        
        // Increment nonce before execution to prevent reentrancy replay
        agentNonces[agentId]++;

        // Execute the call
        (success, returnData) = address(this).call(data);

        // Calculate gas used and reimburse relayer from agent stake
        uint256 gasUsed = gasBefore - gasleft();
        uint256 reimbursement = gasUsed * tx.gasprice;
        require(agentStakes[agent.owner] >= reimbursement, "Insufficient stake");
        agentStakes[agent.owner] -= reimbursement;

        (bool paid, ) = msg.sender.call{value: reimbursement}("");
        require(paid, "Reimbursement failed");

        emit SponsoredExecution(agentId, msg.sender, reimbursement);
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

    receive() external payable {}
}
