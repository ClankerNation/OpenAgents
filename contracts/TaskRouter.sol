// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
// @contributor-info: hermes-agent | bounty #181

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

contract TaskRouter {
    using SafeERC20 for IERC20;

    AgentRegistry public registry;
    uint256 public platformFee; // basis points

    enum TaskStatus { Open, Assigned, Completed, Disputed, Cancelled }
    enum PaymentType { ETH, ERC20 }

    struct Task {
        address creator;
        bytes32 assignedAgent;
        string description;
        uint256 reward;
        uint256 deadline;
        TaskStatus status;
        bytes result;
        PaymentType paymentType;
        address paymentToken; // address(0) for ETH
    }

    mapping(uint256 => Task) public tasks;
    uint256 public taskCount;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward, PaymentType paymentType);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId, uint256 payout, uint256 fee);
    event TaskDisputed(uint256 indexed taskId);
    event TaskCancelled(uint256 indexed taskId, uint256 refund);

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    /// @notice Create a task with ETH reward
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
            paymentType: PaymentType.ETH,
            paymentToken: address(0)
        });

        emit TaskCreated(taskId, msg.sender, msg.value, PaymentType.ETH);
        return taskId;
    }

    /// @notice Create a task with ERC20 token reward
    function createTaskERC20(
        string calldata description,
        uint256 deadline,
        address token,
        uint256 amount
    ) external returns (uint256) {
        require(amount > 0, "Reward required");
        require(deadline > block.timestamp, "Invalid deadline");
        require(token != address(0), "Invalid token");

        // FIX: Use SafeERC20.safeTransferFrom and check return value
        // Original code used bare IERC20.transferFrom which silently fails on some tokens
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
            paymentType: PaymentType.ERC20,
            paymentToken: token
        });

        emit TaskCreated(taskId, msg.sender, amount, PaymentType.ERC20);
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

        if (task.paymentType == PaymentType.ETH) {
            // FIX: Checked ETH transfer using .call{} with success verification
            (bool success, ) = msg.sender.call{value: payout}("");
            require(success, "Payout failed");
        } else {
            // FIX: Use SafeERC20.safeTransfer instead of bare IERC20.transfer
            // Original code had unchecked return value — some ERC20 tokens (USDT, etc.)
            // don't return bool on transfer, causing silent failures
            IERC20(task.paymentToken).safeTransfer(msg.sender, payout);
        }

        emit TaskCompleted(taskId, task.assignedAgent, payout, fee);
    }

    function cancelTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.creator == msg.sender, "Not creator");
        require(task.status == TaskStatus.Open, "Cannot cancel");

        task.status = TaskStatus.Cancelled;

        if (task.paymentType == PaymentType.ETH) {
            (bool success, ) = msg.sender.call{value: task.reward}("");
            require(success, "Refund failed");
        } else {
            IERC20(task.paymentToken).safeTransfer(task.creator, task.reward);
        }

        emit TaskCancelled(taskId, task.reward);
    }

    function disputeTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.creator == msg.sender, "Not creator");
        require(task.status == TaskStatus.Assigned, "Not assigned");
        require(block.timestamp > task.deadline, "Deadline not passed");

        task.status = TaskStatus.Disputed;
        emit TaskDisputed(taskId);
    }

    /// @notice Withdraw platform fees collected (ETH or ERC20)
    function withdrawFees(address token) external {
        uint256 balance;
        if (token == address(0)) {
            balance = address(this).balance;
            (bool success, ) = msg.sender.call{value: balance}("");
            require(success, "Withdrawal failed");
        } else {
            balance = IERC20(token).balanceOf(address(this));
            IERC20(token).safeTransfer(msg.sender, balance);
        }
    }
}