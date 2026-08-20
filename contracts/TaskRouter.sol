// @contributor rafaio1
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

    // Multi-sig approval for large payouts
    uint256 public constant LARGE_PAYOUT_THRESHOLD = 1 ether;
    address[3] public approvers;
    mapping(uint256 => mapping(address => bool)) public payoutApprovals;
    mapping(uint256 => uint256) public payoutApprovalCount;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event PayoutApproved(uint256 indexed taskId, address indexed approver, uint256 approvalCount);
    event PayoutExecuted(uint256 indexed taskId, address indexed recipient, uint256 amount);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);

    constructor(address _registry, uint256 _platformFee, address[3] memory _approvers) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
        approvers = _approvers;
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

        // For large payouts, require 2-of-3 multi-sig approval
        if (payout >= LARGE_PAYOUT_THRESHOLD) {
            // Store pending payout; must be approved via approvePayment
            emit TaskCompleted(taskId, task.assignedAgent);
            return;
        }

        (bool success, ) = msg.sender.call{value: payout}("");
        require(success, "Payout failed");

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    /// @notice Approve a large payout. Requires 2 of 3 designated approvers.
    /// @param taskId The completed task with pending large payout.
    function approvePayment(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Completed, "Task not completed");

        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;
        require(payout >= LARGE_PAYOUT_THRESHOLD, "Below threshold");

        // Verify caller is a designated approver
        bool isApprover = false;
        for (uint256 i = 0; i < 3; i++) {
            if (approvers[i] == msg.sender) {
                isApprover = true;
                break;
            }
        }
        require(isApprover, "Not authorized approver");
        require(!payoutApprovals[taskId][msg.sender], "Already approved");

        payoutApprovals[taskId][msg.sender] = true;
        payoutApprovalCount[taskId]++;

        emit PayoutApproved(taskId, msg.sender, payoutApprovalCount[taskId]);

        // Execute payout once 2 approvals reached
        if (payoutApprovalCount[taskId] >= 2) {
            AgentRegistry.Agent memory agent = registry.getAgent(task.assignedAgent);
            (bool success, ) = agent.owner.call{value: payout}("");
            require(success, "Payout failed");
            emit PayoutExecuted(taskId, agent.owner, payout);
        }
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
}
