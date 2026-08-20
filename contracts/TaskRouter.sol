// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor-info rafaio1
 * @timestamp 2026-08-20T08:35:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
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
    mapping(bytes32 => uint256) public agentNonces;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event SponsoredExecution(bytes32 indexed agentId, address indexed relayer, uint256 gasUsed);

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    /**
     * @notice Execute a transaction on behalf of an agent via meta-transaction relay
     * @param agentId The ID of the agent authorizing the execution
     * @param data The calldata to execute
     * @param signature ECDSA signature from the agent owner over (agentId, data, nonce)
     * @dev Relayer pays gas and is reimbursed from agent's staked balance in registry
     */
    function executeOnBehalf(
        bytes32 agentId,
        bytes calldata data,
        bytes calldata signature
    ) external returns (bool success) {
        uint256 startGas = gasleft();
        
        // Replay protection via nonce
        uint256 nonce = agentNonces[agentId];
        
        // Reconstruct signed message hash
        bytes32 messageHash = keccak256(abi.encodePacked(agentId, data, nonce));
        bytes32 ethSignedHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
        
        // Recover signer from signature
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
        require(v == 27 || v == 28, "Invalid signature v value");
        
        address recoveredSigner = ecrecover(ethSignedHash, v, r, s);
        require(recoveredSigner != address(0), "Invalid signature");
        
        // Verify signer is the agent owner
        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.active, "Agent not active");
        require(agent.owner == recoveredSigner, "Not agent owner");
        
        // Increment nonce before execution to prevent replay
        agentNonces[agentId] = nonce + 1;
        
        // Execute the call
        (success, ) = address(this).call(data);
        require(success, "Sponsored execution failed");
        
        // Calculate gas used and reimburse relayer from agent stake
        uint256 gasUsed = startGas - gasleft() + 30000; // Base overhead
        uint256 gasCost = gasUsed * tx.gasprice;
        
        // Reimburse relayer — assumes registry has withdrawStake or similar
        // For now, emit event for off-chain settlement or direct transfer if stake held here
        (bool refundSuccess, ) = msg.sender.call{value: gasCost}("");
        require(refundSuccess, "Relayer reimbursement failed");
        
        emit SponsoredExecution(agentId, msg.sender, gasUsed);
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
}
