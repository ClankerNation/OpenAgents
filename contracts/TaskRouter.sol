// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "./AgentRegistry.sol";

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
    mapping(address => uint256) public stakeBalances;
    mapping(address => uint256) public nonces;

    uint256 public taskCount;
    uint256 public platformFee; // basis points

    uint256 private constant RELAY_OVERHEAD = 45000;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event StakeDeposited(address indexed agent, uint256 amount);
    event StakeWithdrawn(address indexed agent, uint256 amount);
    event RelayExecuted(address indexed agent, address indexed relayer, uint256 indexed nonce, uint256 reimbursement);

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    function createTask(string calldata description, uint256 deadline) external payable returns (uint256) {
        return _createTask(description, deadline, msg.value, msg.sender);
    }

    function assignTask(uint256 taskId, bytes32 agentId) external {
        _assignTask(taskId, agentId, msg.sender);
    }

    function completeTask(uint256 taskId, bytes calldata result) external {
        _completeTask(taskId, result, msg.sender);
    }

    function cancelTask(uint256 taskId) external {
        _cancelTask(taskId, msg.sender);
    }

    function disputeTask(uint256 taskId) external {
        _disputeTask(taskId, msg.sender);
    }

    function depositStake() external payable {
        require(msg.value > 0, "Stake required");
        stakeBalances[msg.sender] += msg.value;
        emit StakeDeposited(msg.sender, msg.value);
    }

    function withdrawStake(uint256 amount) external {
        require(amount > 0, "Amount required");
        require(stakeBalances[msg.sender] >= amount, "Insufficient stake");

        stakeBalances[msg.sender] -= amount;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Withdraw failed");

        emit StakeWithdrawn(msg.sender, amount);
    }

    function executeOnBehalf(address agent, bytes calldata data, bytes calldata signature) external returns (bytes memory) {
        require(agent != address(0), "Invalid agent");

        uint256 gasStart = gasleft();
        uint256 nonce = nonces[agent];
        _verifySignature(agent, data, nonce, signature);

        nonces[agent] = nonce + 1;

        bytes4 selector;
        assembly {
            selector := calldataload(data.offset)
        }

        if (selector == this.assignTask.selector) {
            (uint256 taskId, bytes32 agentId) = abi.decode(data[4:], (uint256, bytes32));
            _assignTask(taskId, agentId, agent);
        } else if (selector == this.completeTask.selector) {
            (uint256 taskId, bytes memory result) = abi.decode(data[4:], (uint256, bytes));
            _completeTask(taskId, result, agent);
        } else if (selector == this.disputeTask.selector) {
            (uint256 taskId) = abi.decode(data[4:], (uint256));
            _disputeTask(taskId, agent);
        } else if (selector == this.cancelTask.selector) {
            (uint256 taskId) = abi.decode(data[4:], (uint256));
            _cancelTask(taskId, agent);
        } else {
            revert("Unsupported call");
        }

        uint256 gasUsed = gasStart - gasleft() + RELAY_OVERHEAD;
        uint256 reimbursement = gasUsed * tx.gasprice;
        require(stakeBalances[agent] >= reimbursement, "Insufficient stake");

        stakeBalances[agent] -= reimbursement;
        (bool refunded, ) = msg.sender.call{value: reimbursement}("");
        require(refunded, "Reimburse failed");

        emit RelayExecuted(agent, msg.sender, nonce, reimbursement);

        return "";
    }

    function _createTask(
        string calldata description,
        uint256 deadline,
        uint256 reward,
        address creator
    ) internal returns (uint256) {
        require(reward > 0, "Reward required");
        require(deadline > block.timestamp, "Invalid deadline");

        uint256 taskId = taskCount++;
        tasks[taskId] = Task({
            creator: creator,
            assignedAgent: bytes32(0),
            description: description,
            reward: reward,
            deadline: deadline,
            status: TaskStatus.Open,
            result: ""
        });

        emit TaskCreated(taskId, creator, reward);
        return taskId;
    }

    function _assignTask(uint256 taskId, bytes32 agentId, address actor) internal {
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Open, "Not open");
        require(block.timestamp < task.deadline, "Deadline passed");

        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.active, "Agent not active");
        require(agent.owner == actor, "Not agent owner");

        task.assignedAgent = agentId;
        task.status = TaskStatus.Assigned;

        emit TaskAssigned(taskId, agentId);
    }

    function _completeTask(uint256 taskId, bytes memory result, address actor) internal {
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Assigned, "Not assigned");

        AgentRegistry.Agent memory agent = registry.getAgent(task.assignedAgent);
        require(agent.owner == actor, "Not assigned agent owner");

        task.result = result;
        task.status = TaskStatus.Completed;

        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;

        (bool success, ) = actor.call{value: payout}("");
        require(success, "Payout failed");

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    function _cancelTask(uint256 taskId, address actor) internal {
        Task storage task = tasks[taskId];
        require(task.creator == actor, "Not creator");
        require(task.status == TaskStatus.Open, "Cannot cancel");

        task.status = TaskStatus.Cancelled;
        (bool success, ) = actor.call{value: task.reward}("");
        require(success, "Refund failed");
    }

    function _disputeTask(uint256 taskId, address actor) internal {
        Task storage task = tasks[taskId];
        require(task.creator == actor, "Not creator");
        require(task.status == TaskStatus.Assigned, "Not assigned");
        require(block.timestamp > task.deadline, "Deadline not passed");

        task.status = TaskStatus.Disputed;
        emit TaskDisputed(taskId);
    }

    function _verifySignature(address agent, bytes calldata data, uint256 nonce, bytes calldata signature) internal view {
        bytes32 messageHash = keccak256(abi.encode(address(this), block.chainid, agent, nonce, keccak256(data)));
        bytes32 digest = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));

        address signer = digest.recover(signature);
        require(signer == agent, "Invalid signature");
    }
}
