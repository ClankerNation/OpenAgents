// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

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
    event SponsoredExecution(bytes32 indexed agentId, address indexed relayer, uint256 gasReimbursement);


    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);

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

    /**
     * @notice Execute a task operation on behalf of an agent via meta-transaction.
     * @param agentId The agent's bytes32 identifier
     * @param data The calldata to execute (e.g., encoded completeTask call)
     * @param signature ECDSA signature from the agent over keccak256(abi.encodePacked(agentId, nonce, data))
     */
    function executeOnBehalf(
        bytes32 agentId,
        bytes calldata data,
        bytes calldata signature
    ) external {
        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.active, "Agent not active");

        // Replay protection: verify nonce
        uint256 currentNonce = agentNonces[agentId];
        bytes32 digest = keccak256(abi.encodePacked(agentId, currentNonce, data));
        address signer = ECDSA.recover(digest, signature);
        require(signer == agent.owner, "Invalid signature");

        // Increment nonce before execution to prevent reentrancy-based replay
        agentNonces[agentId] = currentNonce + 1;

        // Execute the delegated call
        (bool success, bytes memory returnData) = address(this).call(data);
        require(success, string(returnData));

        // Reimburse relayer from agent's staked balance
        uint256 gasUsed = tx.gasprice * (gasleft() + 50000); // approximate with buffer
        uint256 stakeBalance = registry.getStake(agentId);
        require(stakeBalance >= gasUsed, "Insufficient stake for gas");
        registry.deductStake(agentId, gasUsed);

        (bool reimbursed, ) = msg.sender.call{value: gasUsed}("");
        require(reimbursed, "Relayer reimbursement failed");

        emit SponsoredExecution(agentId, msg.sender, gasUsed);
    }

}
