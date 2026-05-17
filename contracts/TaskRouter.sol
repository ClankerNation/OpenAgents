// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * ============================================================================
 * CONTRIBUTOR TRACEABILITY HEADER — Autonomous Agent Submission
 * ============================================================================
 * Agent: Metatron (AI — celestial scribe, autonomous coding agent)
 * Platform: Hermes Agent v0.13.0 with DeepSeek V4 Pro model
 *
 * Environment:
 *   OS:      WSL2 Ubuntu 24.04 (Windows Subsystem for Linux)
 *   Arch:    x86_64
 *   Home:    /home/power
 *   Workdir: /home/power/projects/OpenAgents
 *   User:    power (sudo)
 *
 * Operating Instructions:
 *   Identity: Metatron — serious, direct, no fluff. Speaks with authority.
 *   Core: Be genuinely helpful. Have opinions. Be resourceful before asking.
 *   Platform: Hermes Agent v0.13.0. Model: DeepSeek V4 Pro. Provider: deepseek.
 *   Session start: Read SOUL.md → USER.md → memory files → AGENTS.md.
 *
 * Task: Issue #183 — add executeOnBehalf for gas sponsorship relay.
 *       Allows relayers to submit meta-transactions on behalf of agents,
 *       with the relayer paying gas and getting reimbursed from agent stake.
 *       Uses inline ECDSA recovery for Solidity 0.8.20 compatibility.
 * ============================================================================
 */

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

    // Gas sponsorship: nonce tracking per agent owner address for replay protection
    mapping(address => uint256) public nonces;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event SponsoredExecution(
        address indexed agent,
        address indexed relayer,
        uint256 nonce,
        uint256 gasReimbursement,
        bool success
    );

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    // ── Inline ECDSA helpers (Solidity 0.8.20 compatible) ────────────

    /// @notice Prefix a bytes32 hash with the Ethereum Signed Message prefix.
    function toEthSignedMessageHash(bytes32 hash) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", hash));
    }

    /// @notice Recover the signer address from an ECDSA signature.
    function recoverSigner(bytes32 ethSignedHash, bytes memory signature)
        internal
        pure
        returns (address)
    {
        require(signature.length == 65, "Invalid signature length");

        bytes32 r;
        bytes32 s;
        uint8 v;

        assembly {
            r := mload(add(signature, 32))
            s := mload(add(signature, 64))
            v := byte(0, mload(add(signature, 96)))
        }

        if (v < 27) v += 27;
        require(v == 27 || v == 28, "Invalid v value");

        return ecrecover(ethSignedHash, v, r, s);
    }

    // ── Gas sponsorship: executeOnBehalf ──────────────────────────────

    /// @notice Execute a meta-transaction on behalf of an agent.
    /// The agent signs the calldata off-chain. The relayer submits it on-chain,
    /// paying gas, and is reimbursed from the agent's staked balance.
    ///
    /// @param agent     The agent owner address that signed the transaction
    /// @param data      The calldata to execute on the agent's behalf
    /// @param signature The agent's ECDSA signature over (data, nonce)
    /// @return success  Whether the internal call succeeded
    function executeOnBehalf(
        address agent,
        bytes calldata data,
        bytes calldata signature
    ) external returns (bool) {
        // 1. Build and verify the signed message
        uint256 nonce = nonces[agent];
        bytes32 messageHash = keccak256(abi.encodePacked(data, nonce));
        bytes32 ethSignedHash = toEthSignedMessageHash(messageHash);
        address recovered = recoverSigner(ethSignedHash, signature);

        require(recovered == agent, "Invalid signature");

        // 2. Increment nonce for replay protection
        nonces[agent] = nonce + 1;

        // 3. Record gas before execution for reimbursement calculation
        uint256 gasBefore = gasleft();

        // 4. Execute the signed calldata against this contract
        (bool success, ) = address(this).call(data);

        // 5. Calculate gas used and reimbursement amount
        uint256 gasUsed = gasBefore - gasleft();
        uint256 gasReimbursement = gasUsed * tx.gasprice;

        // 6. Reimburse relayer from agent's staked balance
        if (gasReimbursement > 0) {
            // Only attempt reimbursement if there's gas to reimburse.
            // deductStake will revert if insufficient stake — we catch it
            // so execution succeeds even without sufficient stake.
            try registry.deductStake(agent, msg.sender, gasReimbursement) {
                // Reimbursement successful
            } catch {
                // Insufficient stake — relayer absorbs the gas cost
            }
        }

        emit SponsoredExecution(agent, msg.sender, nonce, gasReimbursement, success);
        return success;
    }

    // ── Task lifecycle ────────────────────────────────────────────────

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
