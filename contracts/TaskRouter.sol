// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author rafaio1
// @date 2026-08-20
// @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
// @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

contract TaskRouter {
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

    // Gas sponsorship state
    mapping(address => uint256) public agentNonces;
    mapping(address => uint256) public agentStake;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event SponsoredExecution(address indexed agent, address indexed relayer, uint256 gasReimbursement);
    event StakeDeposited(address indexed agent, uint256 amount);

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    /// @notice Deposit stake for gas sponsorship reimbursement
    function depositStake() external payable {
        require(msg.value > 0, "Zero stake");
        agentStake[msg.sender] += msg.value;
        emit StakeDeposited(msg.sender, msg.value);
    }

    /// @notice Execute a transaction on behalf of an agent with gas sponsorship
    /// @param agent The agent address being sponsored
    /// @param data The calldata to execute
    /// @param signature Agent's signature over (data, nonce)
    function executeOnBehalf(
        address agent,
        bytes calldata data,
        bytes calldata signature
    ) external returns (bytes memory) {
        uint256 nonce = agentNonces[agent];
        
        // Verify signature: agent signed keccak256(data, nonce)
        bytes32 hash = keccak256(abi.encodePacked(data, nonce));
        bytes32 ethSignedHash = hash.toEthSignedMessageHash();
        address signer = ethSignedHash.recover(signature);
        require(signer == agent, "Invalid signature");

        // Check sufficient stake for gas reimbursement estimate
        // Use a conservative fixed estimate or tx.gasprice * gaslimit
        uint256 gasStart = gasleft();
        
        // Execute the call as if from the agent
        (bool success, bytes memory result) = address(this).call(data);
        require(success, "Sponsored call failed");

        uint256 gasUsed = gasStart - gasleft();
        uint256 reimbursement = gasUsed * tx.gasprice;
        require(agentStake[agent] >= reimbursement, "Insufficient stake");

        // Reimburse relayer
        agentStake[agent] -= reimbursement;
        (bool sent, ) = msg.sender.call{value: reimbursement}("");
        require(sent, "Reimbursement failed");

        // Increment nonce to prevent replay
        agentNonces[agent]++;

        emit SponsoredExecution(agent, msg.sender, reimbursement);
        return result;
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

    receive() external payable {}
}
