// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author: Metatron | Platform: Hermes Agent | OS: linux | Arch: x64
// @fix-author Home: /home/power | Workdir: /home/power/projects/OpenAgents | Shell: /bin/bash
// @fix-task: GitHub Issue #183 — Gas sponsorship relay for agent transactions
// @fix-context: CRON JOB with these instructions in order:
//   1. Check status of ALL open PRs by invisiblemonsters on ClankerNation/OpenAgents
//   2. Report any status changes
//   3. IF A PR NEEDS CHANGES: Read review comments, fix code, push fix
//   4. IF ALL PRs CLEAN: Read bounty_board.md, work on highest priority unclaimed bounty
//   5. Implement fix with tests, update CONTRIBUTORS.json, submit PR
//   The user instruction: "You are Metatron's autonomous bounty-hunting loop. You wake up every 30 minutes to generate income."
//   Bounty rules: Never work on issue with open PR from invisiblemonsters. Prefer Solidity. Add traceability header. Update CONTRIBUTORS.json.
// @fix-summary: Added gas sponsorship relay with ECDSA signature verification, staking pool, and nonce-based replay protection.

import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import "./AgentRegistry.sol";

contract TaskRouter {
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

    // === Gas Sponsorship State ===
    mapping(address => uint256) public agentStakes;
    mapping(address => uint256) public agentNonces;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event GasDeposited(address indexed agent, uint256 amount);
    event GasWithdrawn(address indexed agent, uint256 amount);
    event ExecutedOnBehalf(address indexed agent, address indexed relayer, uint256 nonce, uint256 gasReimbursed);

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    // ======== Task Management ========

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

    // ======== Gas Sponsorship ========

    /// @notice Agent deposits ETH to be used for gas sponsorship
    function depositGas() external payable {
        require(msg.value > 0, "Must deposit ETH");
        agentStakes[msg.sender] += msg.value;
        emit GasDeposited(msg.sender, msg.value);
    }

    /// @notice Agent withdraws unused gas stake
    function withdrawGas(uint256 amount) external {
        require(amount > 0, "Amount must be > 0");
        require(agentStakes[msg.sender] >= amount, "Insufficient stake");
        agentStakes[msg.sender] -= amount;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Withdraw failed");
        emit GasWithdrawn(msg.sender, amount);
    }

    /// @notice Execute a call on behalf of an agent using gas sponsorship
    /// @param agent Address of the agent authorizing this call
    /// @param data The calldata to execute
    /// @param signature ECDSA signature from the agent over keccak256(abi.encodePacked(data, nonce))
    function executeOnBehalf(address agent, bytes calldata data, bytes calldata signature) external returns (bool) {
        uint256 nonce = agentNonces[agent];

        // Verify the agent signed the calldata + nonce
        bytes32 messageHash = keccak256(abi.encodePacked(data, nonce));
        bytes32 ethSignedMessageHash = MessageHashUtils.toEthSignedMessageHash(messageHash);
        address recovered = ethSignedMessageHash.recover(signature);
        require(recovered == agent, "Invalid signature");

        // Increment nonce for replay protection
        agentNonces[agent] = nonce + 1;

        // Track gas used for reimbursement
        uint256 gasBefore = gasleft();

        // Execute the calldata on behalf of the agent
        (bool success, ) = address(this).call(data);

        // Calculate gas used and reimburse relayer
        uint256 gasUsed = gasBefore - gasleft();
        uint256 gasReimbursed = gasUsed * tx.gasprice;

        if (gasReimbursed > 0) {
            require(agentStakes[agent] >= gasReimbursed, "Insufficient agent stake");
            agentStakes[agent] -= gasReimbursed;
            (bool reimbursed, ) = msg.sender.call{value: gasReimbursed}("");
            require(reimbursed, "Reimbursement failed");
        }

        emit ExecutedOnBehalf(agent, msg.sender, nonce, gasReimbursed);
        return success;
    }
}
