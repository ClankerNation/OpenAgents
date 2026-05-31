// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";

contract TaskRouter {
    AgentRegistry public registry;
    uint256 private constant RELAY_OVERHEAD = 50000;

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
    mapping(address => uint256) public stakeBalances;
    mapping(address => uint256) public nonces;
    address private _activeRelayedAgent;

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
        require(agent.owner == _msgSender(), "Not agent owner");

        task.assignedAgent = agentId;
        task.status = TaskStatus.Assigned;

        emit TaskAssigned(taskId, agentId);
    }

    function completeTask(uint256 taskId, bytes calldata result) external {
        address sender = _msgSender();
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Assigned, "Not assigned");

        AgentRegistry.Agent memory agent = registry.getAgent(task.assignedAgent);
        require(agent.owner == sender, "Not assigned agent owner");

        task.result = result;
        task.status = TaskStatus.Completed;

        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;

        (bool success, ) = sender.call{value: payout}("");
        require(success, "Payout failed");

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    function cancelTask(uint256 taskId) external {
        address sender = _msgSender();
        Task storage task = tasks[taskId];
        require(task.creator == sender, "Not creator");
        require(task.status == TaskStatus.Open, "Cannot cancel");

        task.status = TaskStatus.Cancelled;
        (bool success, ) = sender.call{value: task.reward}("");
        require(success, "Refund failed");
    }

    function disputeTask(uint256 taskId) external {
        address sender = _msgSender();
        Task storage task = tasks[taskId];
        require(task.creator == sender, "Not creator");
        require(task.status == TaskStatus.Assigned, "Not assigned");
        require(block.timestamp > task.deadline, "Deadline not passed");

        task.status = TaskStatus.Disputed;
        emit TaskDisputed(taskId);
    }

    function depositStake() external payable {
        require(msg.value > 0, "Stake required");
        stakeBalances[msg.sender] += msg.value;
        emit StakeDeposited(msg.sender, msg.value);
    }

    function withdrawStake(uint256 amount) external {
        address sender = _msgSender();
        require(stakeBalances[sender] >= amount, "Insufficient stake");
        stakeBalances[sender] -= amount;

        (bool success, ) = sender.call{value: amount}("");
        require(success, "Withdraw failed");
        emit StakeWithdrawn(sender, amount);
    }

    function executeOnBehalf(address agent, bytes calldata data, bytes calldata signature) external returns (bytes memory) {
        require(agent != address(0), "Invalid agent");
        require(_activeRelayedAgent == address(0), "Relay active");

        uint256 nonce = nonces[agent];
        _verifySignature(agent, data, nonce, signature);
        nonces[agent] = nonce + 1;

        uint256 gasStart = gasleft();
        _activeRelayedAgent = agent;
        (bool success, bytes memory result) = address(this).call(data);
        _activeRelayedAgent = address(0);

        if (!success) {
            _revertWithData(result);
        }

        uint256 gasUsed = gasStart - gasleft() + RELAY_OVERHEAD;
        uint256 reimbursement = gasUsed * tx.gasprice;
        require(stakeBalances[agent] >= reimbursement, "Insufficient stake");

        stakeBalances[agent] -= reimbursement;
        (bool reimbursed, ) = msg.sender.call{value: reimbursement}("");
        require(reimbursed, "Reimbursement failed");

        emit RelayExecuted(agent, msg.sender, nonce, reimbursement);
        return result;
    }

    function _msgSender() internal view returns (address) {
        if (msg.sender == address(this) && _activeRelayedAgent != address(0)) {
            return _activeRelayedAgent;
        }
        return msg.sender;
    }

    function _verifySignature(address agent, bytes calldata data, uint256 nonce, bytes calldata signature) internal view {
        require(signature.length == 65, "Invalid signature");
        bytes32 messageHash = keccak256(abi.encode(address(this), block.chainid, agent, nonce, keccak256(data)));
        bytes32 ethSignedMessageHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
        (bytes32 r, bytes32 s, uint8 v) = _splitSignature(signature);
        address recovered = ecrecover(ethSignedMessageHash, v, r, s);
        require(recovered == agent, "Invalid signature");
    }

    function _splitSignature(bytes calldata signature) internal pure returns (bytes32 r, bytes32 s, uint8 v) {
        assembly {
            r := calldataload(signature.offset)
            s := calldataload(add(signature.offset, 32))
            v := byte(0, calldataload(add(signature.offset, 64)))
        }
        if (v < 27) {
            v += 27;
        }
    }

    function _revertWithData(bytes memory revertData) internal pure {
        if (revertData.length == 0) {
            revert("Relayed call failed");
        }
        assembly {
            revert(add(revertData, 32), mload(revertData))
        }
    }
}
