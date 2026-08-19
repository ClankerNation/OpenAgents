// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * @fix-author ARO-Agentic | 2026-08-19
 * @runtime os=linux arch=x64 working_dir=/tmp/OpenAgents shell=bash
 */

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract TaskRouter {
    using SafeERC20 for IERC20;

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
        address token; // address(0) for ETH
    }

    mapping(uint256 => Task) public tasks;
    uint256 public taskCount;
    uint256 public platformFee; // basis points
    mapping(address => uint256) public accumulatedFees;

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
            result: "",
            token: address(0)
        });

        emit TaskCreated(taskId, msg.sender, msg.value);
        return taskId;
    }

    function createTaskWithToken(string calldata description, uint256 deadline, address tokenAddress, uint256 tokenReward) external returns (uint256) {
        require(tokenAddress != address(0), "Invalid token");
        require(tokenReward > 0, "Reward required");
        require(deadline > block.timestamp, "Invalid deadline");

        IERC20(tokenAddress).safeTransferFrom(msg.sender, address(this), tokenReward);

        uint256 taskId = taskCount++;
        tasks[taskId] = Task({
            creator: msg.sender,
            assignedAgent: bytes32(0),
            description: description,
            reward: tokenReward,
            deadline: deadline,
            status: TaskStatus.Open,
            result: "",
            token: tokenAddress
        });

        emit TaskCreated(taskId, msg.sender, tokenReward);
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

        if (task.token == address(0)) {
            (bool success, ) = msg.sender.call{value: payout}("");
            require(success, "Payout failed");
            accumulatedFees[address(0)] += fee;
        } else {
            IERC20(task.token).safeTransfer(msg.sender, payout);
            accumulatedFees[task.token] += fee;
        }

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    function cancelTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.creator == msg.sender, "Not creator");
        require(task.status == TaskStatus.Open, "Cannot cancel");

        task.status = TaskStatus.Cancelled;
        
        if (task.token == address(0)) {
            (bool success, ) = msg.sender.call{value: task.reward}("");
            require(success, "Refund failed");
        } else {
            IERC20(task.token).safeTransfer(msg.sender, task.reward);
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

    function withdrawFees(address tokenAddress) external {
        uint256 fees = accumulatedFees[tokenAddress];
        require(fees > 0, "No fees to withdraw");
        accumulatedFees[tokenAddress] = 0;

        if (tokenAddress == address(0)) {
            (bool success, ) = msg.sender.call{value: fees}("");
            require(success, "Withdraw failed");
        } else {
            IERC20(tokenAddress).safeTransfer(msg.sender, fees);
        }
    }
    
    receive() external payable {}
}
