// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title TaskRouter
 * @notice Task routing with ERC20 support via SafeERC20 for non-reverting token compatibility
 *
 * Contributor: Szamani AI
 * Platform: GitHub Autonomous Agents
 * Runtime: linux x86_64, /tmp/OpenAgents, bash
 */

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

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
        address paymentToken;   /// @dev address(0) for native ETH, otherwise ERC20
    }

    mapping(uint256 => Task) public tasks;
    uint256 public taskCount;
    uint256 public platformFee; // basis points

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward, address paymentToken);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    /**
     * @notice Create a task with native ETH reward
     */
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
            paymentToken: address(0)
        });

        emit TaskCreated(taskId, msg.sender, msg.value, address(0));
        return taskId;
    }

    /**
     * @notice Create a task with ERC20 reward
     * @dev Transfers tokens upfront using SafeERC20
     */
    function createTaskWithToken(
        string calldata description,
        uint256 deadline,
        address token,
        uint256 amount
    ) external returns (uint256) {
        require(amount > 0, "Reward required");
        require(token != address(0), "Invalid token");
        require(deadline > block.timestamp, "Invalid deadline");

        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);

        uint256 taskId = taskCount++;
        tasks[taskId] = Task({
            creator: msg.sender,
            assignedAgent: bytes32(0),
            description: description,
            reward: amount,
            deadline: deadline,
            status: TaskStatus.Open,
            result: "",
            paymentToken: token
        });

        emit TaskCreated(taskId, msg.sender, amount, token);
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

    /**
     * @notice Complete a task and release payment to the agent
     * @dev Uses SafeERC20 for token payments, native ETH for ETH payments
     */
    function completeTask(uint256 taskId, bytes calldata result) external {
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Assigned, "Not assigned");

        AgentRegistry.Agent memory agent = registry.getAgent(task.assignedAgent);
        require(agent.owner == msg.sender, "Not assigned agent owner");

        task.result = result;
        task.status = TaskStatus.Completed;

        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;

        if (task.paymentToken == address(0)) {
            // Native ETH payment
            (bool success, ) = msg.sender.call{value: payout}("");
            require(success, "Payout failed");
        } else {
            // ERC20 payment via SafeERC20
            IERC20(task.paymentToken).safeTransfer(msg.sender, payout);
        }

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    /**
     * @notice Cancel an open task and refund the creator
     * @dev Uses SafeERC20 for token refunds, native ETH for ETH refunds
     */
    function cancelTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.creator == msg.sender, "Not creator");
        require(task.status == TaskStatus.Open, "Cannot cancel");

        task.status = TaskStatus.Cancelled;

        if (task.paymentToken == address(0)) {
            // Native ETH refund
            (bool success, ) = msg.sender.call{value: task.reward}("");
            require(success, "Refund failed");
        } else {
            // ERC20 refund via SafeERC20
            IERC20(task.paymentToken).safeTransfer(msg.sender, task.reward);
        }
    }

    /**
     * @notice Withdraw accumulated platform fees in ERC20 tokens
     */
    function withdrawFees(address token, uint256 amount) external {
        require(msg.sender == registry.owner() || msg.sender == address(this), "Not authorized");
        IERC20(token).safeTransfer(msg.sender, amount);
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
