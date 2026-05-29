// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";

contract TaskRouter {
    AgentRegistry public registry;
    address private sponsoredExecutor;

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
    mapping(address => uint256) public agentNonces;
    mapping(address => uint256) public agentStake;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event StakeDeposited(address indexed agent, uint256 amount);
    event StakeWithdrawn(address indexed agent, uint256 amount);
    event SponsoredExecution(address indexed agent, address indexed relayer, uint256 nonce, uint256 reimbursement);

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
        address executor = sponsoredExecutor == address(0) ? msg.sender : sponsoredExecutor;
        require(agent.owner == executor, "Not assigned agent owner");

        task.result = result;
        task.status = TaskStatus.Completed;

        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;

        (bool success, ) = executor.call{value: payout}("");
        require(success, "Payout failed");

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    function depositStake() external payable {
        require(msg.value > 0, "Stake required");
        agentStake[msg.sender] += msg.value;
        emit StakeDeposited(msg.sender, msg.value);
    }

    function withdrawStake(uint256 amount) external {
        require(agentStake[msg.sender] >= amount, "Insufficient stake");
        agentStake[msg.sender] -= amount;

        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Withdraw failed");

        emit StakeWithdrawn(msg.sender, amount);
    }

    function executeOnBehalf(
        address agent,
        bytes calldata callData,
        bytes calldata signature
    ) external returns (bytes memory result) {
        require(agent != address(0), "Invalid agent");
        require(sponsoredExecutor == address(0), "Nested sponsorship");

        uint256 startGas = gasleft();
        uint256 nonce = agentNonces[agent];
        bytes32 digest = _sponsoredDigest(agent, callData, nonce);
        require(_recoverSigner(digest, signature) == agent, "Invalid signature");

        agentNonces[agent] = nonce + 1;
        sponsoredExecutor = agent;

        bool success;
        (success, result) = address(this).call(callData);
        sponsoredExecutor = address(0);
        require(success, "Sponsored call failed");

        uint256 reimbursement = (startGas - gasleft() + 21000) * tx.gasprice;
        require(agentStake[agent] >= reimbursement, "Insufficient stake");
        agentStake[agent] -= reimbursement;

        (bool paid, ) = msg.sender.call{value: reimbursement}("");
        require(paid, "Reimbursement failed");

        emit SponsoredExecution(agent, msg.sender, nonce, reimbursement);
    }

    function sponsoredDigest(
        address agent,
        bytes calldata callData,
        uint256 nonce
    ) external view returns (bytes32) {
        return _sponsoredDigest(agent, callData, nonce);
    }

    function _sponsoredDigest(
        address agent,
        bytes calldata callData,
        uint256 nonce
    ) internal view returns (bytes32) {
        bytes32 messageHash = keccak256(abi.encodePacked(block.chainid, address(this), agent, nonce, callData));
        return keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
    }

    function _recoverSigner(bytes32 digest, bytes calldata signature) internal pure returns (address) {
        require(signature.length == 65, "Invalid signature length");
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(signature.offset)
            s := calldataload(add(signature.offset, 32))
            v := byte(0, calldataload(add(signature.offset, 64)))
        }
        return ecrecover(digest, v, r, s);
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
