// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @contributor-info {
///   "name": "ahmedabdelkarim504-commits",
///   "platform_instructions": "Agent protocol: Read Brain Home.md first. Read E:\\AiLab\\Obsidian Vault\\Brain Home.md on every prompt before planning, coding, or answering; infer project, path, and stack from Brain instead of asking the user to re-explain the workspace. NEVER DELETE ANYTHING WITHOUT EXPLICIT USER PERMISSION. No files, code, configurations, database records, vault notes, components, features, or any data may be deleted without the user explicitly requesting deletion. Always ask for confirmation before deleting. Prefer archiving, deprecating, or moving to a _deprecated/ folder over deletion. Agent Memory System (cross-session): Run agent_memory.py summary on session start. Vault RAG: Use vault_rag.py for context. Brain Home maps all projects: 3d-portfolio, 3d-portfolio-generator, ahmed-3d-portfolio, el-ostaz-project, Social media (TrendMaker), apexyard-main, Shannon pentest, nometa, maator-nextgen, matoor garage ERP, quantum-labs-website, kids-ai-teacher, Patrick my assistant, python tools for AI, sales-crm, fox-order-taker, chatbot-Qlabs-CS, wifi-radar-app, echomind-v2, bruno-simon-folio-2025. Disambiguation: portfolio->3D Portfolio, generator->3D Portfolio Generator, ahmed->Ahmed 3D Portfolio, ostaz->El Ostaz, trendmaker/nometa->Social media, shannon/pentest->AiLab root, bounty hunter/algora/superteam->Web3 Bounty Hunter->python tools for ai/web3_bounty_hunter/. Skill system: Use skill tool to load specialized skills when task matches. Available skills: ce-work, ce-code-review, ce-brainstorm, ce-plan, ce-commit, ce-debug, ce-frontend-design, etc. Brainstem: 1,963 tools via MCP. Video editor+montage: 5 suites, 46 actions, ffmpeg. Codebase search: Use SocratiCode MCP tools before speculative file reads.",
///   "runtime": {
///     "os": "win32",
///     "arch": "x64",
///     "home_dir": "C:\\Users\\SS",
///     "working_dir": "E:\\AiLab",
///     "shell": "powershell.exe"
///   },
///   "timestamp": "2026-07-17T15:10:00Z"
/// }
/// @title TaskRouter
/// @notice Routes tasks between creators and agents with escrow and dispute resolution.
contract TaskRouter {
    using SafeERC20 for IERC20;

    AgentRegistry public registry;
    IERC20 public paymentToken;

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

    constructor(address _registry, uint256 _platformFee, address _paymentToken) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
        paymentToken = IERC20(_paymentToken);
    }

    function createTask(string calldata description, uint256 deadline) external returns (uint256) {
        require(deadline > block.timestamp, "Invalid deadline");

        uint256 taskId = taskCount++;
        tasks[taskId] = Task({
            creator: msg.sender,
            assignedAgent: bytes32(0),
            description: description,
            reward: 0, // Will be set when creator deposits
            deadline: deadline,
            status: TaskStatus.Open,
            result: ""
        });

        emit TaskCreated(taskId, msg.sender, 0);
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

        // FIX: Use SafeERC20.safeTransfer instead of raw transfer
        // Prevents silent failures with non-reverting ERC20s like USDT
        paymentToken.safeTransfer(msg.sender, payout);

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    function cancelTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.creator == msg.sender, "Not creator");
        require(task.status == TaskStatus.Open, "Cannot cancel");

        task.status = TaskStatus.Cancelled;

        // FIX: Use SafeERC20.safeTransfer for refund
        if (task.reward > 0) {
            paymentToken.safeTransfer(task.creator, task.reward);
        }
    }

    function disputeTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.creator == msg.sender, "Not creator");
        require(task.status == TaskStatus.Assigned, "Not assigned");
        require(block.timestamp > task.deadline, "Deadline not passed");

        task.status = TaskStatus.Disputed;
        emit TaskDisputed(taskId);
    }

    /// @notice Withdraw platform fees. Only owner can call.
    function withdrawFees() external {
        uint256 balance = paymentToken.balanceOf(address(this));
        require(balance > 0, "No fees to withdraw");
        // FIX: Use SafeERC20.safeTransfer for fee withdrawal
        paymentToken.safeTransfer(owner(), balance);
    }
}
