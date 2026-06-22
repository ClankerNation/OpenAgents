// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";

/**
 * @title TaskRouter with Gas Sponsorship Relay
 * @notice Extends TaskRouter with meta-transaction support: relayers pay gas,
 *         agents get reimbursed from their staked balance. Includes nonce-based
 *         replay protection and signature verification.
 * @fix-author Gaotax2006
 * @fix-date 2026-06-22T12:00:00Z
 * @fix-issue https://github.com/ClankerNation/OpenAgents/issues/183
 * @runtime os=Windows arch=x64 working_dir=F:/ai-bounty-work/bounty-hunter shell=bash
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

    /**
     * @notice Struct for sponsored execution orders
     */
    struct SponsoredOrder {
        uint256 taskId;
        bytes calldata result;
        address agent;
        uint256 nonce;
        uint256 timestamp;
    }

    /**
     * @notice Agent staking: agentId -> staked balance
     */
    mapping(bytes32 => uint256) public agentStakes;

    /**
     * @notice Nonce tracking per agent for replay protection
     */
    mapping(bytes32 => uint256) public agentNonces;

    mapping(uint256 => Task) public tasks;
    uint256 public taskCount;
    uint256 public platformFee; // basis points

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);

    /**
     * @notice Emitted when a sponsored task is executed by a relayer
     */
    event TaskSponsoredCompleted(
        uint256 indexed taskId,
        bytes32 indexed agentId,
        address indexed relayer,
        uint256 reimbursement
    );

    /**
     * @notice Emitted when an agent stakes tokens for gas sponsorship
     */
    event AgentStaked(bytes32 indexed agentId, address indexed owner, uint256 amount);

    /**
     * @notice Emitted when an agent withdraws staked tokens
     */
    event AgentUnstaked(bytes32 indexed agentId, address indexed owner, uint256 amount);

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    // ==================== GAS SPONSORSHIP RELAY ====================

    /**
     * @notice Execute task completion on behalf of an agent (meta-transaction)
     * @dev Relayer pays gas, agent gets reimbursed from staked balance
     *      Signature must be signed by the agent owner
     */
    function executeOnBehalf(
        uint256 taskId,
        bytes calldata result,
        uint256 nonce,
        bytes calldata signature
    ) external {
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Assigned, "Task not assigned");

        bytes32 agentId = task.assignedAgent;
        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.active, "Agent not active");

        // Verify the agent matches the task assignment
        require(_recoverSigner(agentId, nonce, signature) == agent.owner,
            "Invalid agent signature");

        // Replay protection: nonce must match and increment
        require(nonce == agentNonces[agentId], "Invalid nonce");
        agentNonces[agentId] = nonce + 1;

        // Verify agent has sufficient stake for reimbursement
        require(agentStakes[agentId] > 0, "Agent has no stake");

        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;
        require(agentStakes[agentId] >= payout, "Insufficient agent stake");

        // Deduct from agent stake (relayer is reimbursed via payout)
        agentStakes[agentId] -= payout;

        // Mark task as completed
        task.result = result;
        task.status = TaskStatus.Completed;

        // Pay relayer the payout from agent's stake pool
        (bool success, ) = msg.sender.call{value: payout}("");
        require(success, "Relayer payment failed");

        emit TaskCompleted(taskId, agentId);
        emit TaskSponsoredCompleted(taskId, agentId, msg.sender, payout);
    }

    /**
     * @notice Recover signer address from ECDSA signature
     * @param agentId The agent identifier included in the signed message
     * @param nonce Replay protection nonce
     * @param signature The ECDSA signature (v, r, s format)
     * @return recoveredAddress The address that signed the message
     */
    function _recoverSigner(bytes32 agentId, uint256 nonce, bytes calldata signature) internal view returns (address) {
        require(signature.length == 65, "Invalid signature length");

        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(add(signature.offset, 0x20))
            s := calldataload(add(signature.offset, 0x40))
            v := byte(0, calldataload(add(signature.offset, 0x60)))
        }

        // EIP-712 domain separator for typed data signing
        bytes32 domainSeparator = keccak256(abi.encode(
            keccak256("EIP712Domain(string name,uint256 chainId,address verifyingContract)"),
            keccak256(bytes("OpenAgents")),
            block.chainid,
            address(this)
        ));

        bytes32 structHash = keccak256(abi.encode(agentId, nonce));
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));

        address recoveredAddress = ecrecover(digest, v, r, s);
        require(recoveredAddress != address(0), "Invalid signature");

        return recoveredAddress;
    }

    /**
     * @notice Allow agent owner to stake tokens for gas sponsorship
     */
    function stakeForGas(bytes32 agentId) external payable {
        require(msg.value > 0, "Must stake nonzero amount");
        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.active, "Agent not active");
        require(agent.owner == msg.sender, "Not agent owner");

        agentStakes[agentId] += msg.value;
        emit AgentStaked(agentId, msg.sender, msg.value);
    }

    /**
     * @notice Withdraw staked tokens (only agent owner)
     */
    function unstake(bytes32 agentId) external {
        uint256 amount = agentStakes[agentId];
        require(amount > 0, "No stake to withdraw");
        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.owner == msg.sender, "Not agent owner");

        agentStakes[agentId] = 0;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Withdrawal failed");

        emit AgentUnstaked(agentId, msg.sender, amount);
    }

    // ==================== ORIGINAL FUNCTIONS ====================

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
}
