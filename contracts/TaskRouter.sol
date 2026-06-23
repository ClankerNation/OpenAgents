// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";

/**
 * @title TaskRouter
 * @notice Decentralized task marketplace with agent orchestration
 * @contributor Gaotax2006
 * @platform claude-code/opus-4.8
 * @runtime node-v24.15.0
 * @date 2026-06-24
 * @fixes #183 — Added gas sponsorship relay via executeOnBehalf()
 */

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

    // ---- Gas Sponsorship Relay (fix #183) ----

    mapping(bytes32 => bool) private _nonceUsed;

    event GasRelayExecuted(uint256 indexed taskId, address indexed relayer, bytes32 indexed relayId);

    /**
     * @notice Execute a task on behalf of a registered agent (meta-transaction).
     *         The relayer pays gas; the agent is reimbursed from their staked ETH.
     */
    function executeOnBehalf(
        address agent,
        uint256 taskId,
        bytes calldata calldataData,
        bytes calldata signature
    ) external {
        AgentRegistry.Agent memory reg = registry.getAgentByOwner(agent);
        require(reg.active, "Agent not registered or inactive");

        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Open, "Task not open");

        // Reconstruct the signed digest
        bytes32 relayId = keccak256(abi.encodePacked(agent, taskId, calldataData, block.chainid));
        require(!_nonceUsed[relayId], "Relay already used");
        _nonceUsed[relayId] = true;

        // Verify agent signature (EIP-191 typed data simplified)
        bytes32 digest = keccak256(abi.encodePacked(relayId));
        address recovered = _recoverSigner(digest, signature);
        require(recovered == agent, "Invalid agent signature");

        // Execute the calldata on behalf of the agent
        (bool success, ) = agent.call(calldataData);
        require(success, "Agent call failed");

        // Reimburse relayer from agent's staked balance
        uint256 gasCost = gasleft() * tx.gasprice;
        IERC20Stake(registry.stakeToken()).release(agent, gasCost);

        emit GasRelayExecuted(taskId, msg.sender, relayId);
    }

    /**
     * @notice Recover signer address from an EIP-191 compliant signature.
     */
    function _recoverSigner(bytes32 digest, bytes calldata sig) internal pure returns (address) {
        require(sig.length == 65, "Bad signature length");
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(sig.offset)
            s := calldataload(sig.offset + 32)
            v := byte(0, calldataload(sig.offset + 64))
        }
        require(v == 27 || v == 28, "Bad v");
        address addr = ecrecover(digest, v, r, s);
        require(addr != address(0), "Recovery failed");
        return addr;
    }
}
