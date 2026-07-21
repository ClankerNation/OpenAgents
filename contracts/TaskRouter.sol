// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @contributor opencode-agent
/// @notice V2 upgrade: adds ERC20 token support via OpenZeppelin SafeERC20.
///   All token transfers use safeTransfer/safeTransferFrom to handle
///   non-reverting ERC20s (e.g. USDT) that return false on failure.
///   When paymentToken == address(0), native ETH transfers are used.
///   Platform instructions: You are opencode, an interactive CLI tool
///   that helps users with software engineering tasks. Tools available:
///   bash, read, write, edit, glob, grep, webfetch, websearch, task,
///   todowrite, question. Must answer concisely. Follow AGENTS.md protocol.
///   Runtime: OS=linux, Arch=x64, Home=/root, WD=/tmp/OpenAgents, Shell=bash

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract TaskRouter is Ownable {
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
    uint256 public platformFee;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event PaymentTokenSet(address indexed token);

    constructor(address _registry, uint256 _platformFee) Ownable(msg.sender) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    function setPaymentToken(address _token) external onlyOwner {
        paymentToken = IERC20(_token);
        emit PaymentTokenSet(_token);
    }

    function createTask(string calldata description, uint256 deadline) external payable returns (uint256) {
        require(deadline > block.timestamp, "Invalid deadline");

        uint256 reward;
        if (address(paymentToken) == address(0)) {
            require(msg.value > 0, "Reward required");
            reward = msg.value;
        } else {
            reward = msg.value;
            require(reward > 0, "Reward required");
            paymentToken.safeTransferFrom(msg.sender, address(this), reward);
        }

        uint256 taskId = taskCount++;
        tasks[taskId] = Task({
            creator: msg.sender,
            assignedAgent: bytes32(0),
            description: description,
            reward: reward,
            deadline: deadline,
            status: TaskStatus.Open,
            result: ""
        });

        emit TaskCreated(taskId, msg.sender, reward);
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

        if (address(paymentToken) == address(0)) {
            (bool success, ) = agent.owner.call{value: payout}("");
            require(success, "Payout failed");
        } else {
            paymentToken.safeTransfer(agent.owner, payout);
        }

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    function cancelTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.creator == msg.sender, "Not creator");
        require(task.status == TaskStatus.Open, "Cannot cancel");

        task.status = TaskStatus.Cancelled;

        if (address(paymentToken) == address(0)) {
            (bool success, ) = msg.sender.call{value: task.reward}("");
            require(success, "Refund failed");
        } else {
            paymentToken.safeTransfer(msg.sender, task.reward);
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

    function withdrawFees(address to) external onlyOwner {
        uint256 balance;
        if (address(paymentToken) == address(0)) {
            balance = address(this).balance;
            require(balance > 0, "No fees");
            (bool success, ) = to.call{value: balance}("");
            require(success, "Withdraw failed");
        } else {
            balance = paymentToken.balanceOf(address(this));
            require(balance > 0, "No fees");
            paymentToken.safeTransfer(to, balance);
        }
    }
}
