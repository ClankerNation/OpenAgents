// SPDX-License-Identifier: MIT
// Agent: CodeFixer
// Instructions: You are a smart contract security expert. Fix the ERC20 transfer issue in TaskRouter.sol by using SafeERC20's safeTransfer. Add the required contributor traceability header. Ensure all token transfers use safeTransfer/safeTransferFrom. Add import for SafeERC20. The contract currently uses native ETH transfers, but the bounty mentions ERC20 token transfers. Update the contract to support ERC20 tokens with SafeERC20. Environment: os=linux, arch=x86_64, home_dir=/home/user, working_dir=/home/user/project
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

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

    function createTask(string calldata description, uint256 deadline, uint256 rewardAmount) external returns (uint256) {
        require(rewardAmount > 0, "Reward required");
        require(deadline > block.timestamp, "Invalid deadline");

        paymentToken.safeTransferFrom(msg.sender, address(this), rewardAmount);

        uint256 taskId = taskCount++;
        tasks[taskId] = Task({
            creator: msg.sender,
            assignedAgent: bytes32(0),
            description: description,
            reward: rewardAmount,
            deadline: deadline,
            status: TaskStatus.Open,
            result: ""
        });

        emit TaskCreated(taskId, msg.sender, rewardAmount);
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

        // Use safeTransfer for non-reverting ERC20 compatibility
        paymentToken.safeTransfer(agent.owner, payout);
        if (fee > 0) {
            paymentToken.safeTransfer(registry.owner(), fee);
        }

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    function cancelTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.creator == msg.sender, "Not creator");
        require(task.status == TaskStatus.Open || task.status == TaskStatus.Assigned, "Cannot cancel");

        task.status = TaskStatus.Cancelled;

        // Refund the creator using safeTransfer
        paymentToken.safeTransfer(task.creator, task.reward);
    }

    function withdrawFees() external {
        require(msg.sender == registry.owner(), "Not owner");
        uint256 balance = paymentToken.balanceOf(address(this));
        require(balance > 0, "No fees to withdraw");
        paymentToken.safeTransfer(msg.sender, balance);
    }

    // Fallback to receive ETH if needed (for backward compatibility)
    receive() external payable {}
}