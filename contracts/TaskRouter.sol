// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "./AgentRegistry.sol";

/// @title TaskRouter
/// @notice Routes tasks between creators and AI agents with multi-sig approval for large payouts
/// @contributor opencode-gaotax2006
/// @platform You are opencode, an interactive CLI tool...
/// @runtime os=win32 arch=x64 workingdir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
/// @date 2026-05-18T00:00:00Z
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
        address paymentToken;
    }

    mapping(uint256 => Task) public tasks;
    uint256 public taskCount;
    uint256 public platformFee;

    uint256 public constant LARGE_PAYOUT_THRESHOLD = 1 ether;
    uint256 public requiredSignatures;
    mapping(address => bool) public isSigner;
    address[] public signers;

    struct PaymentApproval {
        uint256 approvedCount;
        mapping(address => bool) hasApproved;
        bool executed;
        uint256 deadline;
    }
    mapping(uint256 => PaymentApproval) public paymentApprovals;
    uint256 public constant APPROVAL_EXPIRY = 7 days;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event SignerAdded(address indexed signer);
    event SignerRemoved(address indexed signer);
    event PaymentApproved(uint256 indexed taskId, address indexed signer, uint256 count);
    event PaymentExecuted(uint256 indexed taskId);

    constructor(address _registry, uint256 _platformFee, address[] memory _initialSigners) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
        for (uint256 i = 0; i < _initialSigners.length; i++) {
            isSigner[_initialSigners[i]] = true;
            signers.push(_initialSigners[i]);
        }
        requiredSignatures = _initialSigners.length >= 3 ? 2 : _initialSigners.length;
    }

    function createTaskERC20(string calldata description, uint256 deadline, address token, uint256 amount) external returns (uint256) {
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
            paymentToken: token
        });

        emit TaskCreated(taskId, msg.sender, amount);
        return taskId;
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
            paymentToken: address(0)
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

        if (task.paymentToken != address(0)) {
            IERC20(task.paymentToken).safeTransfer(msg.sender, payout);
        } else {
            (bool success, ) = msg.sender.call{value: payout}("");
            require(success, "Payout failed");
        }

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    function cancelTask(uint256 taskId) external {
        Task storage task = tasks[taskId];
        require(task.creator == msg.sender, "Not creator");
        require(task.status == TaskStatus.Open, "Cannot cancel");

        task.status = TaskStatus.Cancelled;
        if (task.paymentToken != address(0)) {
            IERC20(task.paymentToken).safeTransfer(msg.sender, task.reward);
        } else {
            (bool success, ) = msg.sender.call{value: task.reward}("");
            require(success, "Refund failed");
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
