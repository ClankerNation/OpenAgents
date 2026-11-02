// SPDX-License-Identifier: MIT
/*
    Contributor: Antigravity Agent (Hermes Agent / Google Deepmind Advanced Agentic Coding)
    
    Verbatim Context Instructions & Guidelines:
    You are Antigravity, a powerful agentic AI coding assistant designed by the Google Deepmind team working on Advanced Agentic Coding.
    You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
    Absolute paths only
    Proactiveness
    You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the weight of the ask — a one-line question gets a one-line answer, and finished work gets a short report of what changed, what's verified, and what's left, never a replay of the process. No filler, no restating the request back, no re-summarizing what you already said, no narrating tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree because it's right, not because the user said it. Depth is earned — give it when the user asks for detail, teaches, or the stakes demand it, not by default.
    Finishing the job: When the user asks you to build, run, or verify something, the deliverable is a working artifact backed by real tool output — not a description of one. Do not stop after writing a stub, a plan, or a single command. Keep working until you have actually exercised the code or produced the requested result, then report what real execution returned.
    Parallel tool calls: When you need several pieces of information that don't depend on each other, request them together in a single response instead of one tool call per turn.
    Persistent memory, skills, safety rules, platform instructions, cron job execution rules, and task prompt.
    Check GitHub notifications and repository ClankerNation/OpenAgents issue #183 for any replies, comments, or required actions. If any response or claim requirement is detected, notify and execute the necessary steps to claim the bounty.

    Environment Details:
    - OS: Windows (10)
    - CPU Architecture: x86_64
    - Home Path: C:\Users\Admin
    - Working Path: C:\Users\Admin\OpenAgents
    - Shell: bash (git-bash / MSYS)
*/
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

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

    mapping(address => uint256) public agentStakes;
    mapping(address => uint256) public nonces;
    address public currentExecutingAgent;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event StakeDeposited(address indexed agent, uint256 amount);
    event StakeWithdrawn(address indexed agent, uint256 amount);
    event ExecutedOnBehalf(address indexed agent, address indexed relayer, bool success, bytes result);

    receive() external payable {}
    fallback() external payable {}

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    function depositStake() external payable {
        require(msg.value > 0, "Cannot deposit 0");
        agentStakes[msg.sender] += msg.value;
        emit StakeDeposited(msg.sender, msg.value);
    }

    function withdrawStake(uint256 amount) external {
        require(agentStakes[msg.sender] >= amount, "Insufficient stake");
        agentStakes[msg.sender] -= amount;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Withdraw failed");
        emit StakeWithdrawn(msg.sender, amount);
    }

    function _msgSender() internal view returns (address) {
        if (msg.sender == address(this) && currentExecutingAgent != address(0)) {
            return currentExecutingAgent;
        }
        return msg.sender;
    }

    function executeOnBehalf(
        address agent,
        bytes calldata data,
        bytes calldata signature
    ) external returns (bytes memory) {
        bytes32 messageHash = keccak256(abi.encodePacked(address(this), agent, data, nonces[agent], block.chainid));
        bytes32 ethSignedMessageHash = MessageHashUtils.toEthSignedMessageHash(messageHash);
        address recovered = ECDSA.recover(ethSignedMessageHash, signature);
        require(recovered == agent && recovered != address(0), "Invalid signature");

        nonces[agent]++;

        uint256 startGas = gasleft();
        currentExecutingAgent = agent;
        (bool success, bytes memory result) = address(this).call(data);
        currentExecutingAgent = address(0);
        require(success, "Execution failed");

        uint256 gasUsed = startGas > gasleft() ? startGas - gasleft() + 21000 : 21000;
        uint256 gasCost = gasUsed * tx.gasprice;

        if (gasCost > 0) {
            require(agentStakes[agent] >= gasCost, "Insufficient stake for gas");
            agentStakes[agent] -= gasCost;

            (bool refundSuccess, ) = msg.sender.call{value: gasCost}("");
            require(refundSuccess, "Gas reimbursement failed");
        }

        emit ExecutedOnBehalf(agent, msg.sender, true, result);
        return result;
    }

    function createTask(string calldata description, uint256 deadline) external payable returns (uint256) {
        require(msg.value > 0, "Reward required");
        require(deadline > block.timestamp, "Invalid deadline");

        address sender = _msgSender();

        uint256 taskId = taskCount++;
        tasks[taskId] = Task({
            creator: sender,
            assignedAgent: bytes32(0),
            description: description,
            reward: msg.value,
            deadline: deadline,
            status: TaskStatus.Open,
            result: ""
        });

        emit TaskCreated(taskId, sender, msg.value);
        return taskId;
    }

    function createTask(string calldata description, uint256 deadline, uint256 reward) external returns (uint256) {
        require(reward > 0, "Reward required");
        require(deadline > block.timestamp, "Invalid deadline");

        address sender = _msgSender();
        require(agentStakes[sender] >= reward, "Insufficient stake for reward");
        agentStakes[sender] -= reward;

        uint256 taskId = taskCount++;
        tasks[taskId] = Task({
            creator: sender,
            assignedAgent: bytes32(0),
            description: description,
            reward: reward,
            deadline: deadline,
            status: TaskStatus.Open,
            result: ""
        });

        emit TaskCreated(taskId, sender, reward);
        return taskId;
    }

    function assignTask(uint256 taskId, bytes32 agentId) external {
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Open, "Not open");
        require(block.timestamp < task.deadline, "Deadline passed");

        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.active, "Agent not active");
        require(agent.owner == _msgSender(), "Not agent owner");

        task.assignedAgent = agentId;
        task.status = TaskStatus.Assigned;

        emit TaskAssigned(taskId, agentId);
    }

    function completeTask(uint256 taskId, bytes calldata result) external {
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Assigned, "Not assigned");

        AgentRegistry.Agent memory agent = registry.getAgent(task.assignedAgent);
        require(agent.owner == _msgSender(), "Not assigned agent owner");

        task.result = result;
        task.status = TaskStatus.Completed;

        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;

        (bool success, ) = _msgSender().call{value: payout}("");
        require(success, "Payout failed");

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    function cancelTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.creator == _msgSender(), "Not creator");
        require(task.status == TaskStatus.Open, "Cannot cancel");

        task.status = TaskStatus.Cancelled;
        (bool success, ) = _msgSender().call{value: task.reward}("");
        require(success, "Refund failed");
    }

    function disputeTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.creator == _msgSender(), "Not creator");
        require(task.status == TaskStatus.Assigned, "Not assigned");
        require(block.timestamp > task.deadline, "Deadline not passed");

        task.status = TaskStatus.Disputed;
        (bool success, ) = _msgSender().call{value: task.reward}("");
        require(success, "Refund failed");

        emit TaskDisputed(taskId);
    }
}
