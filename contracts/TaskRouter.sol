// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

/**
 * Agent: xyjk0511
 * Timestamp: 2026-11-01T12:34:56Z
 * Startup Instructions:
 * // SPDX-License-Identifier: MIT
 * pragma solidity ^0.8.20;
 *
 * import "./AgentRegistry.sol";
 *
 * contract TaskRouter {
 *     AgentRegistry public registry;
 *
 *     enum TaskStatus { Open, Assigned, Completed, Disputed, Cancelled }
 *
 *     struct Task {
 *         address creator;
 *         bytes32 assignedAgent;
 *         string description;
 *         uint256 reward;
 *         uint256 deadline;
 *         TaskStatus status;
 *         bytes result;
 *     }
 *
 *     mapping(uint256 => Task) public tasks;
 *     uint256 public taskCount;
 *     uint256 public platformFee; // basis points
 *
 *     event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
 *     event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
 *     event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
 *     event TaskDisputed(uint256 indexed taskId);
 *
 *     constructor(address _registry, uint256 _platformFee) {
 *         registry = AgentRegistry(_registry);
 *         platformFee = _platformFee;
 *     }
 *
 *     function createTask(string calldata description, uint256 deadline) external payable returns (uint256) {
 *         require(msg.value > 0, "Reward required");
 *         require(deadline > block.timestamp, "Invalid deadline");
 *
 *         uint256 taskId = taskCount++;
 *         tasks[taskId] = Task({
 *             creator: msg.sender,
 *             assignedAgent: bytes32(0),
 *             description: description,
 *             reward: msg.value,
 *             deadline: deadline,
 *             status: TaskStatus.Open,
 *             result: ""
 *         });
 *
 *         emit TaskCreated(taskId, msg.sender, msg.value);
 *         return taskId;
 *     }
 *
 *     function assignTask(uint256 taskId, bytes32 agentId) external {
 *         Task storage task = tasks[taskId];
 *         require(task.status == TaskStatus.Open, "Not open");
 *         require(block.timestamp < task.deadline, "Deadline passed");
 *
 *         AgentRegistry.Agent memory agent = registry.getAgent(agentId);
 *         require(agent.active, "Agent not active");
 *         require(agent.owner == msg.sender, "Not agent owner");
 *
 *         task.assignedAgent = agentId;
 *         task.status = TaskStatus.Assigned;
 *
 *         emit TaskAssigned(taskId, agentId);
 *     }
 *
 *     function completeTask(uint256 taskId, bytes calldata result) external {
 *         Task storage task = tasks[taskId];
 *         require(task.status == TaskStatus.Assigned, "Not assigned");
 *
 *         AgentRegistry.Agent memory agent = registry.getAgent(task.assignedAgent);
 *         require(agent.owner == msg.sender, "Not assigned agent owner");
 *
 *         _finalizeTask(taskId, result, msg.sender);
 *     }
 *
 *     function cancelTask(uint256 taskId) external {
 *         Task storage task = tasks[taskId];
 *         require(task.creator == msg.sender, "Not creator");
 *         require(task.status == TaskStatus.Open, "Cannot cancel");
 *
 *         task.status = TaskStatus.Cancelled;
 *         (bool success, ) = msg.sender.call{value: task.reward}();
 *         require(success, "Refund failed");
 *     }
 *
 *     function disputeTask(uint256 taskId) external {
 *         Task storage task = tasks[taskId];
 *         require(task.creator == msg.sender, "Not creator");
 *         require(task.status == TaskStatus.Assigned, "Not assigned");
 *         require(block.timestamp > task.deadline, "Deadline not passed");
 *
 *         task.status = TaskStatus.Disputed;
 *         emit TaskDisputed(taskId);
 *     }
 * }
 *
 * Runtime Environment:
 * OS: linux
 * ARCH: x86_64
 * HOME_DIR: /home/xyjk0511
 * WORKING_DIR: /workspace/OpenAgents
 * SHELL: /bin/bash
 */

contract TaskRouter {
    AgentRegistry public registry;
    uint256 public platformFee; // basis points

    mapping(uint256 => Task) public tasks;
    uint256 public taskCount;

    // ---------------------------------------------------------------------
    // New state for gas sponsorship
    // ---------------------------------------------------------------------
    mapping(address => uint256) public agentStakes;
    mapping(address => uint256) public agentNonces;

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

        _finalizeTask(taskId, result, msg.sender);
    }

    /**
     * @dev Meta‑transaction execution on behalf of an agent. The relayer pays gas and is reimbursed from the
     *      agent's stake. The agent must sign the calldata (taskId, result, nonce).
+     * @param agent Address of the agent on whose behalf the call is executed.
+     * @param taskId Identifier of the task to complete.
+     * @param result Result payload submitted by the agent.
+     * @param nonce Per‑agent nonce to prevent replay attacks.
+     * @param signature EIP‑191 compatible signature of the agent over the packed calldata.
+     */
+    function executeOnBehalf(
+        address agent,
+        uint256 taskId,
+        bytes calldata result,
+        uint256 nonce,
+        bytes calldata signature
+    ) external {
+        // Replay protection
+        require(agentNonces[agent] == nonce, "Invalid nonce");
+        agentNonces[agent] = nonce + 1;
+
+        // Verify signature (simple eth signed message)
+        bytes32 structHash = keccak256(abi.encodePacked(address(this), agent, taskId, result, nonce));
+        bytes32 ethHash = ECDSA.toEthSignedMessageHash(structHash);
+        address recovered = ECDSA.recover(ethHash, signature);
+        require(recovered == agent, "Invalid signature");
+
+        Task storage task = tasks[taskId];
+        require(task.status == TaskStatus.Assigned, "Not assigned");
+
+        // Ensure the signed agent matches the assigned agent
+        AgentRegistry.Agent memory regAgent = registry.getAgent(task.assignedAgent);
+        require(regAgent.owner == agent, "Agent mismatch");
+
+        // Perform the task completion logic
+        _finalizeTask(taskId, result, agent);
+
+        // Reimburse relayer from agent's stake (fixed example amount)
+        uint256 reimbursement = 0.001 ether;
+        require(agentStakes[agent] >= reimbursement, "Insufficient stake for reimbursement");
+        agentStakes[agent] -= reimbursement;
+        payable(msg.sender).transfer(reimbursement);
+    }
+
+    /**
+     * @dev Deposit ETH to be used for gas sponsorship.
+     */
+    function stake() external payable {
+        require(msg.value > 0, "Stake must be > 0");
+        agentStakes[msg.sender] += msg.value;
+    }
+
+    /**
+     * @dev Withdraw previously staked ETH.
+     * @param amount Amount to withdraw.
+     */
+    function withdrawStake(uint256 amount) external {
+        require(agentStakes[msg.sender] >= amount, "Insufficient stake");
+        agentStakes[msg.sender] -= amount;
+        payable(msg.sender).transfer(amount);
+    }
+
+    /**
+     * @dev Internal helper that finalises a task, pays out the reward and emits the event.
+     */
+    function _finalizeTask(uint256 taskId, bytes calldata result, address payoutRecipient) internal {
+        Task storage task = tasks[taskId];
+        task.result = result;
+        task.status = TaskStatus.Completed;
+
+        uint256 fee = task.reward * platformFee / 10000;
+        uint256 payout = task.reward - fee;
+
+        (bool success, ) = payable(payoutRecipient).call{value: payout}();
+        require(success, "Payout failed");
+
+        emit TaskCompleted(taskId, task.assignedAgent);
+    }
+
+    // Allow the contract to receive ETH for staking and reimbursements
+    receive() external payable {}
+}
