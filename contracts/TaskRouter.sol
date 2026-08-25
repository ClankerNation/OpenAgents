// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
// @fix-author rafaio1
// @date 2026-08-25T01:25:00Z
// @runtime linux x64 /tmp/openagents_issue_202 bash
// @platform-config Agentic bounty-hunter workflow
// @startup-instructions Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement, senior dev multi-agent orchestration, and Wise payout integration.

import "./AgentRegistry.sol";

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

    // --- Gas Sponsorship Relay (Issue #190) ---
    mapping(bytes32 => uint256) public agentNonces;

    event GasSponsoredExecution(bytes32 indexed agentId, address indexed relayer, uint256 gasReimbursement);

    /// @notice Execute a task operation on behalf of an agent via meta-transaction.
    /// @param agentId The agent's registry ID.
    /// @param data Encoded calldata for the task operation (e.g., completeTask).
    /// @param nonce Agent's current nonce for replay protection.
    /// @param signature ECDSA signature over keccak256(abi.encodePacked(agentId, data, nonce, address(this))).
    /// @dev Relayer pays gas; agent is reimbursed from their staked balance in AgentRegistry.
    function executeOnBehalf(
        bytes32 agentId,
        bytes calldata data,
        uint256 nonce,
        bytes calldata signature
    ) external {
        require(agentNonces[agentId] == nonce, "TaskRouter: invalid nonce");
        agentNonces[agentId] = nonce + 1;

        bytes32 digest = keccak256(abi.encodePacked(agentId, data, nonce, address(this)));
        bytes32 ethSignedHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", digest));

        (bytes32 r, bytes32 s, uint8 v) = _splitSignature(signature);
        address signer = ecrecover(ethSignedHash, v, r, s);
        require(signer != address(0), "TaskRouter: invalid signature");

        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.owner == signer, "TaskRouter: signer mismatch");

        uint256 gasBefore = gasleft();
        (bool success, ) = address(this).call(data);
        require(success, "TaskRouter: sponsored call failed");
        uint256 gasUsed = gasBefore - gasleft() + 30000; // base overhead

        uint256 reimbursement = gasUsed * tx.gasprice;
        require(agent.stake >= reimbursement, "TaskRouter: insufficient stake for gas");

        registry.deductStake(agentId, reimbursement);
        (bool sent, ) = msg.sender.call{value: reimbursement}("");
        require(sent, "TaskRouter: reimbursement transfer failed");

        emit GasSponsoredExecution(agentId, msg.sender, reimbursement);
    }

    function _splitSignature(bytes calldata sig) internal pure returns (bytes32 r, bytes32 s, uint8 v) {
        require(sig.length == 65, "TaskRouter: invalid signature length");
        assembly {
            r := calldataload(sig.offset)
            s := calldataload(add(sig.offset, 32))
            v := byte(0, calldataload(add(sig.offset, 64)))
        }
        if (v < 27) v += 27;
        require(v == 27 || v == 28, "TaskRouter: invalid v value");
    }
}
