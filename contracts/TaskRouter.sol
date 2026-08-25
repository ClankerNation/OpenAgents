// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";

// @fix-author rafaio1
// @date 2026-08-25T00:00:00Z
// @runtime linux x64 /tmp/openagents_issue_183 bash
// @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement

contract TaskRouter is EIP712 {
    using ECDSA for bytes32;

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
    mapping(bytes32 => uint256) private _nonces;
    uint256 public gasReimbursementRate; // wei per gas unit

    bytes32 private constant EXECUTE_TYPEHASH = keccak256("ExecuteOnBehalf(address target,uint256 value,bytes data,uint256 nonce,uint256 deadline)");

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event GasSponsoredExecution(bytes32 indexed agentId, address indexed target, uint256 gasUsed);

    constructor(address _registry, uint256 _platformFee, uint256 _gasRate) EIP712("TaskRouter", "1") {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
        gasReimbursementRate = _gasRate;
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

    /**
     * @notice Execute a call on behalf of an agent with gas sponsorship
     * @dev Implements meta-transaction relay with ECDSA verification and nonce replay protection
     * @param agentId The agent identifier sponsoring the gas
     * @param target Target contract address to call
     * @param value ETH value to send with the call
     * @param data Calldata for the target contract
     * @param deadline Signature expiration timestamp
     * @param signature ECDSA signature from the agent owner
     */
    function executeOnBehalf(
        bytes32 agentId,
        address target,
        uint256 value,
        bytes calldata data,
        uint256 deadline,
        bytes calldata signature
    ) external {
        require(block.timestamp <= deadline, "Signature expired");
        require(target != address(this), "Invalid target");

        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.active, "Agent not active");

        uint256 currentNonce = _nonces[agentId];
        bytes32 structHash = keccak256(abi.encode(EXECUTE_TYPEHASH, target, value, keccak256(data), currentNonce, deadline));
        bytes32 digest = _hashTypedDataV4(structHash);
        address signer = digest.recover(signature);

        require(signer == agent.owner, "Invalid signature");

        _nonces[agentId] = currentNonce + 1;

        uint256 gasStart = gasleft();
        (bool success, ) = target.call{value: value}(data);
        require(success, "Execution failed");
        uint256 gasUsed = gasStart - gasleft();

        uint256 reimbursement = gasUsed * gasReimbursementRate;
        require(reimbursement <= agent.stake, "Insufficient stake for gas");

        emit GasSponsoredExecution(agentId, target, gasUsed);
    }

    /**
     * @notice Get current nonce for an agent
     * @param agentId The agent identifier
     * @return Current nonce value
     */
    function getNonce(bytes32 agentId) external view returns (uint256) {
        return _nonces[agentId];
    }
}
