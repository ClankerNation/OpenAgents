// @contributor-info ARO-Agentic
// @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
// @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";

contract TaskRouter is EIP712 {
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
    // Gas sponsorship relay state
    mapping(bytes32 => uint256) public nonces;
    mapping(bytes32 => uint256) public agentStake; // Simplified stake tracking for gas reimbursement
    
    bytes32 private constant EXECUTE_TYPEHASH = keccak256("ExecuteOnBehalf(address agent,bytes calldata,uint256 nonce)");
    
    event GasSponsored(bytes32 indexed agentId, address indexed relayer, uint256 gasUsed);
    event StakeDeposited(bytes32 indexed agentId, uint256 amount);


    constructor(address _registry, uint256 _platformFee) EIP712("OpenAgentsTaskRouter", "1") {
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

    /// @notice Deposit stake for gas sponsorship reimbursement.
    /// @param agentId The agent ID to credit stake to.
    function depositStake(bytes32 agentId) external payable {
        require(msg.value > 0, "Zero stake");
        agentStake[agentId] += msg.value;
        emit StakeDeposited(agentId, msg.value);
    }

    /// @notice Execute a transaction on behalf of an agent using meta-transaction.
    /// @param agent Address of the agent who signed the request.
    /// @param data Encoded calldata to execute.
    /// @param nonce Replay protection nonce.
    /// @param signature ECDSA signature from the agent.
    function executeOnBehalf(
        address agent,
        bytes calldata data,
        uint256 nonce,
        bytes calldata signature
    ) external returns (bytes memory) {
        // Verify nonce
        bytes32 agentId = keccak256(abi.encodePacked(agent));
        require(nonce == nonces[agentId], "Invalid nonce");
        
        // Verify signature using EIP-712
        bytes32 structHash = keccak256(abi.encode(EXECUTE_TYPEHASH, agent, keccak256(data), nonce));
        bytes32 digest = _hashTypedDataV4(structHash);
        address signer = ECDSA.recover(digest, signature);
        require(signer == agent, "Invalid signature");
        
        // Increment nonce to prevent replay
        nonces[agentId]++;
        
        // Execute the call
        uint256 gasBefore = gasleft();
        (bool success, bytes memory result) = address(this).call(data);
        uint256 gasUsed = gasBefore - gasleft();
        
        require(success, "Execution failed");
        
        // Reimburse relayer from agent's stake (simplified: fixed gas price estimate)
        // In production, use block.basefee or oracle price
        uint256 reimbursement = gasUsed * tx.gasprice;
        require(agentStake[agentId] >= reimbursement, "Insufficient stake for gas");
        agentStake[agentId] -= reimbursement;
        
        (bool paid, ) = msg.sender.call{value: reimbursement}("");
        require(paid, "Reimbursement failed");
        
        emit GasSponsored(agentId, msg.sender, gasUsed);
        return result;
    }

}
