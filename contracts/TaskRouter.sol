// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

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
    // Gas sponsorship relay
    mapping(bytes32 => bool) public executedHashes;
    mapping(address => uint256) public agentNonces;

    event TaskRelayed(uint256 indexed taskId, address indexed relayer, bytes32 indexed agentId);

    /// @notice Execute a task on behalf of an agent using gas sponsorship.
    /// @param taskId The task to complete.
    /// @param result The task result bytes.
    /// @param nonce Agent's current nonce for replay protection.
    /// @param signature Agent's ECDSA signature over the task data.
    function executeOnBehalf(
        uint256 taskId,
        bytes calldata result,
        uint256 nonce,
        bytes calldata signature
    ) external {
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Assigned, "TaskRouter: not assigned");

        AgentRegistry.Agent memory agent = registry.getAgent(task.assignedAgent);
        require(agent.active, "TaskRouter: agent not active");

        // Replay protection via nonce
        require(agentNonces[agent.owner] == nonce, "TaskRouter: invalid nonce");
        agentNonces[agent.owner] = nonce + 1;

        // Signature verification
        bytes32 structHash = keccak256(abi.encode(taskId, result.length, nonce));
        bytes32 digest = keccak256(abi.encodePacked("", domainSeparator(), structHash));
        address signer = recoverSigner(signature, digest);
        require(signer == agent.owner, "TaskRouter: invalid agent signature");

        // Relayer pays gas, agent is reimbursed from reward
        task.result = result;
        task.status = TaskStatus.Completed;

        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;

        (bool success, ) = agent.owner.call{value: payout}("");
        require(success, "TaskRouter: payout failed");

        emit TaskCompleted(taskId, task.assignedAgent);
        emit TaskRelayed(taskId, msg.sender, task.assignedAgent);
    }

    bytes32 private _domainSeparator;

    function domainSeparator() internal view returns (bytes32) {
        return _domainSeparator;
    }

    function recoverSigner(bytes calldata signature, bytes32 digest) internal pure returns (address) {
        require(signature.length == 65, "TaskRouter: invalid signature length");
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := mload(add(signature, 32))
            s := mload(add(signature, 64))
            v := byte(0, mload(add(signature, 96)))
        }
        return ecrecover(digest, v, r, s);
    }

}
