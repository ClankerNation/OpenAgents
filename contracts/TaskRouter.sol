// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title TaskRouter
/// @notice Routes tasks between creators and registered agents, escrowing the
/// reward until the task completes (payout to the agent) or is cancelled
/// (refund to the creator). Rewards can be paid in native ETH (original
/// behaviour, unchanged) or in an ERC-20 token via `createTaskERC20`.
/// @dev Fix for issue #181: every ERC-20 transfer in this contract goes
/// through OpenZeppelin `SafeERC20` (`safeTransfer` / `safeTransferFrom`).
/// A non-standard token that returns `false` instead of reverting (e.g.
/// USDT-style) now reverts the whole transaction instead of silently
/// failing while the task is marked complete. Legacy tokens that return no
/// data are tolerated by SafeERC20.
contract TaskRouter {
    using SafeERC20 for IERC20;

    AgentRegistry public registry;

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
        address paymentToken; // address(0) for ETH tasks
    }

    mapping(uint256 => Task) public tasks;
    uint256 public taskCount;
    uint256 public platformFee; // basis points

    /// @notice Platform fees accrued from completed ETH tasks.
    uint256 public feesCollectedETH;
    /// @notice Platform fees accrued from completed ERC-20 tasks, per token.
    mapping(address => uint256) public feesCollected;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event FeesWithdrawn(address indexed recipient, address indexed token, uint256 amount);

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
            paymentType: PaymentType.ETH,
            paymentToken: address(0)
        });

        emit TaskCreated(taskId, msg.sender, msg.value);
        return taskId;
    }

    /// @notice Create a task whose reward is escrowed in an ERC-20 token.
    /// @dev The caller must approve this contract for `amount` first.
    /// `safeTransferFrom` reverts if the token returns `false` or the
    /// transfer otherwise fails, so a task is never created without escrow.
    function createTaskERC20(
        string calldata description,
        uint256 deadline,
        address token,
        uint256 amount
    ) external returns (uint256) {
        require(amount > 0, "Reward required");
        require(deadline > block.timestamp, "Invalid deadline");
        require(token != address(0), "Invalid token");

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

        emit TaskCreated(taskId, msg.sender, amount);
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
            feesCollectedETH += fee;
            (bool success, ) = msg.sender.call{value: payout}("");
            require(success, "Payout failed");
        } else {
            // Fix #181: safeTransfer reverts if a non-reverting token
            // reports failure, so the payout can never silently fail
            // while the task is marked complete.
            feesCollected[task.paymentToken] += fee;
            IERC20(task.paymentToken).safeTransfer(msg.sender, payout);
        }

        emit TaskCompleted(taskId, task.assignedAgent);
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
            // Fix #181: refund via safeTransfer so a `false` return
            // reverts instead of silently keeping the creator's escrow.
            IERC20(task.paymentToken).safeTransfer(task.creator, task.reward);
        }
    }

    /// @notice Withdraw accrued platform fees to the platform admin.
    /// @dev Only the AgentRegistry owner (the platform admin) may call.
    /// Only fees actually accrued via `completeTask` are withdrawable —
    /// escrowed task rewards are never touched. `token == address(0)`
    /// withdraws ETH fees; otherwise the ERC-20 fees for that token.
    function withdrawFees(address token) external {
        require(msg.sender == registry.owner(), "Not admin");

        if (token == address(0)) {
            uint256 amount = feesCollectedETH;
            require(amount > 0, "No fees");
            feesCollectedETH = 0;
            (bool success, ) = msg.sender.call{value: amount}("");
            require(success, "Withdrawal failed");
            emit FeesWithdrawn(msg.sender, token, amount);
        } else {
            uint256 amount = feesCollected[token];
            require(amount > 0, "No fees");
            feesCollected[token] = 0;
            IERC20(token).safeTransfer(msg.sender, amount);
            emit FeesWithdrawn(msg.sender, token, amount);
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
}
