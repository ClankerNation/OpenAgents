// SPDX-License-Identifier: MIT
/*
    Contributor: Antigravity Agent
    
    Verbatim Context Instructions & Guidelines:
    You are Antigravity, a powerful agentic AI coding assistant designed by the Google Deepmind team working on Advanced Agentic Coding.
    You are pair programming with a USER to solve their coding task. Absolute paths only. Proactiveness.
    Finishing the job: build, run, or verify with real tool output. Never fabricate results.
    Parallel tool calls: batch independent reads/searches.
    Persistent memory & skills: use skills when relevant.
    Cron job execution: execute fully and autonomously.

    Environment Details:
    - OS: Windows (10)
    - CPU Architecture: x86_64 / x64
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

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event StakeDeposited(address indexed agent, uint256 amount);
    event StakeWithdrawn(address indexed agent, uint256 amount);
    event ExecutedOnBehalf(address indexed agent, address indexed relayer, bool success);

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
        (bool success, bytes memory result) = address(this).call(data);
        require(success, "Execution failed");

        uint256 gasUsed = startGas - gasleft() + 21000; // estimated overhead
        uint256 gasCost = gasUsed * tx.gasprice;

        require(agentStakes[agent] >= gasCost, "Insufficient stake for gas");
        agentStakes[agent] -= gasCost;

        (bool refundSuccess, ) = msg.sender.call{value: gasCost}("");
        require(refundSuccess, "Gas reimbursement failed");

        emit ExecutedOnBehalf(agent, msg.sender, true);
        return result;
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
}
