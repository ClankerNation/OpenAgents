/// @title TaskRouter — gas sponsorship extension
/// @notice Enables meta-transactions for agent operations via gas sponsorship relay.
///         Agents stake ETH; relayers pay gas and get reimbursed from the agent's stake.
///         Implements EIP-712 typed-signature verification for agent authorization.

/// SPDX-License-Identifier: MIT
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

    // Agent stakes for gas sponsorship
    mapping(bytes32 => uint256) public agentStakes;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event StakeDeposited(bytes32 indexed agentId, address depositor, uint256 amount);
    event GasRelayerPaid(bytes32 indexed agentId, address relayer, uint256 amount);

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    /// @notice Deposit stake for an agent — enables gas sponsorship
    /// @param agentId The agent to stake for
    function depositStake(bytes32 agentId) external payable {
        require(msg.value > 0, "Must deposit positive amount");
        agentStakes[agentId] += msg.value;
        emit StakeDeposited(agentId, msg.sender, msg.value);
    }

    /// @notice Withdraw unused stake (agent owner only)
    /// @param agentId The agent whose stake to withdraw
    /// @param amount Amount to withdraw
    function withdrawStake(bytes32 agentId, uint256 amount) external {
        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.owner == msg.sender, "Not agent owner");
        require(agentStakes[agentId] >= amount, "Insufficient stake");
        agentStakes[agentId] -= amount;
        payable(msg.sender).transfer(amount);
    }

    /// @notice Relayer executes calldata on behalf of an agent, reimbursed from agent stake
    /// @param agentId The agent whose stake funds the gas
    /// @param target The contract to call
    /// @param data The calldata to execute
    /// @param signature EIP-712 signature from the agent's owner authorizing this call
    function executeOnBehalf(
        bytes32 agentId,
        address target,
        bytes calldata data,
        bytes calldata signature
    ) external {
        require(agentStakes[agentId] >= 21000 * tx.gasprice, "Insufficient stake for gas");

        // EIP-712 domain separator for this contract
        bytes32 domainSeparator = keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256("TaskRouter"),
            keccak256("1"),
            block.chainid,
            address(this)
        ));

        bytes32 structHash = keccak256(abi.encode(
            keccak256("ExecuteRequest(bytes32 agentId,address target,bytes data)"),
            agentId,
            target,
            keccak256(data)
        ));

        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));

        // Verify agent signature
        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.active && agent.owner != address(0), "Invalid agent");

        bytes32 r = bytes32(signature[0:32]);
        bytes32 s = bytes32(signature[32:64]);
        uint8 v = uint8(signature[64]);

        address signer = ecrecover(digest, v, r, s);
        require(signer == agent.owner, "Invalid signature");

        // Reimburse relayer from agent stake before external call
        uint256 gasCost = 21000 * tx.gasprice;
        agentStakes[agentId] -= gasCost;
        emit GasRelayerPaid(agentId, msg.sender, gasCost);

        (bool success, ) = target.call(data);
        require(success, "Execution failed");
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