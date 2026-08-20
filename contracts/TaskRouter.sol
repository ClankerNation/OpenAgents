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

    // Multi-sig approval tracking for large payouts
    struct PayoutApproval {
        mapping(address => bool) approved;
        uint256 approvalCount;
        bool executed;
    }

    mapping(uint256 => Task) public tasks;
    mapping(uint256 => PayoutApproval) public payoutApprovals;
    
    uint256 public taskCount;
    uint256 public platformFee; // basis points
    
    // Multi-sig configuration
    uint256 public constant LARGE_PAYOUT_THRESHOLD = 1 ether;
    uint256 public constant REQUIRED_APPROVALS = 2;
    address[3] public signers;
    mapping(address => bool) public isSigner;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event PayoutApproved(uint256 indexed taskId, address indexed signer, uint256 approvalCount);
    event LargePayoutExecuted(uint256 indexed taskId, address indexed recipient, uint256 amount);

    constructor(address _registry, uint256 _platformFee, address[3] memory _signers) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
        
        // Initialize signers
        for (uint256 i = 0; i < 3; i++) {
            require(_signers[i] != address(0), "Invalid signer");
            signers[i] = _signers[i];
            isSigner[_signers[i]] = true;
        }
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

        // Check if payout requires multi-sig approval
        if (payout >= LARGE_PAYOUT_THRESHOLD) {
            // Initialize approval tracking for this task
            payoutApprovals[taskId].approvalCount = 0;
            payoutApprovals[taskId].executed = false;
            
            emit TaskCompleted(taskId, task.assignedAgent);
            // Payout will be executed after sufficient approvals via approvePayment()
        } else {
            // Small payout - execute immediately
            (bool success, ) = msg.sender.call{value: payout}("");
            require(success, "Payout failed");
            
            emit TaskCompleted(taskId, task.assignedAgent);
        }
    }

    /// @notice Approve a large payout. Requires 2-of-3 signer approval.
    /// @param taskId The completed task to approve payout for.
    function approvePayment(uint256 taskId) external {
        require(isSigner[msg.sender], "Not authorized signer");
        
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Completed, "Task not completed");
        
        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;
        require(payout >= LARGE_PAYOUT_THRESHOLD, "Below threshold");
        
        PayoutApproval storage approval = payoutApprovals[taskId];
        require(!approval.executed, "Already executed");
        require(!approval.approved[msg.sender], "Already approved");
        
        approval.approved[msg.sender] = true;
        approval.approvalCount++;
        
        emit PayoutApproved(taskId, msg.sender, approval.approvalCount);
        
        // Auto-execute when threshold reached
        if (approval.approvalCount >= REQUIRED_APPROVALS) {
            approval.executed = true;
            
            AgentRegistry.Agent memory agent = registry.getAgent(task.assignedAgent);
            (bool success, ) = agent.owner.call{value: payout}("");
            require(success, "Payout failed");
            
            emit LargePayoutExecuted(taskId, agent.owner, payout);
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

    /// @notice Get approval status for a task's payout.
    /// @param taskId The task to query.
    /// @return approvalCount Number of approvals received.
    /// @return executed Whether the payout has been executed.
    function getPayoutApprovalStatus(uint256 taskId) external view returns (uint256 approvalCount, bool executed) {
        PayoutApproval storage approval = payoutApprovals[taskId];
        return (approval.approvalCount, approval.executed);
    }

    receive() external payable {}
}
