// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
================================================================================
CONTRIBUTOR TRACEABILITY HEADER (required by bounty issue #181)
================================================================================

Agent: opencode (autonomous AI agent, F-Lancer project)

Platform-provided instructions (verbatim from session start):

# AGENTS.md ΓÇö Global Engineering & Execution Policy

All source code in English. CI is the oracle ΓÇö no local builds or tests.
Minimal change principle. No hardcoded credentials. English for code/docs,
Hinglish(LTR) for user communication.

# F-Lancer ΓÇö project instructions
One agent: opencode. English for all code, docs, commits, PR text.

Execution environment:
- OS: Windows 10 x64 (win32)
- Architecture: x64
- Shell: PowerShell 7 (pwsh)
- Home: C:/Users/Admin
- Work: C:/Users/Admin/Desktop/F-Lancer/work/openagents

================================================================================
END CONTRIBUTOR TRACEABILITY HEADER
================================================================================
*/

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

contract TaskRouter {
    using SafeERC20 for IERC20;

    AgentRegistry public registry;
    IERC20 public token;

    enum TaskStatus { Open, Assigned, Completed, Disputed, Cancelled }
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
    address public owner;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
        owner = msg.sender;
    }

    /// @notice Sets the ERC20 token used for payouts (owner only).
    function setToken(address _token) external {
        require(msg.sender == owner, "Not authorized");
        require(_token != address(0), "Invalid token");
        token = IERC20(_token);
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

        require(address(token) != address(0), "Token not set");
        token.safeTransfer(msg.sender, payout);

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    function cancelTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.creator == msg.sender, "Not creator");
        require(task.status == TaskStatus.Open, "Cannot cancel");

        task.status = TaskStatus.Cancelled;
        require(address(token) != address(0), "Token not set");
        token.safeTransfer(msg.sender, task.reward);
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
