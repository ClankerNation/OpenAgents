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
    mapping(address => uint256) public stakedBalances;
    mapping(address => uint256) public nonces;

    address private _relayedAgent;
    bool private _relayActive;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event StakeDeposited(address indexed agent, uint256 amount);
    event StakeWithdrawn(address indexed agent, uint256 amount);
    event RelayedExecution(address indexed relayer, address indexed agent, bytes4 selector, uint256 reimbursement);

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }

    function depositStake() external payable {
        require(msg.value > 0, "Stake required");
        stakedBalances[msg.sender] += msg.value;
        emit StakeDeposited(msg.sender, msg.value);
    }

    function withdrawStake(uint256 amount) external {
        require(amount > 0, "Amount required");
        require(stakedBalances[msg.sender] >= amount, "Insufficient stake");
        stakedBalances[msg.sender] -= amount;

        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Withdraw failed");
        emit StakeWithdrawn(msg.sender, amount);
    }

    function executeOnBehalf(address agent, bytes calldata callData, bytes calldata signature) external returns (bytes memory) {
        require(agent != address(0), "Invalid agent");
        require(!_relayActive, "Relay busy");
        require(callData.length >= 4, "Invalid calldata");

        uint256 nonce = nonces[agent];
        bytes32 digest = _toEthSignedMessageHash(
            keccak256(abi.encode(address(this), block.chainid, agent, nonce, keccak256(callData)))
        );
        require(_recoverSigner(digest, signature) == agent, "Invalid signature");

        nonces[agent] = nonce + 1;

        uint256 startGas = gasleft();
        _relayActive = true;
        _relayedAgent = agent;

        (bool success, bytes memory returnData) = address(this).call(callData);

        _relayActive = false;
        _relayedAgent = address(0);
        if (!success) {
            assembly {
                revert(add(returnData, 32), mload(returnData))
            }
        }

        uint256 gasUsed = startGas - gasleft() + 45000;
        uint256 reimbursement = gasUsed * tx.gasprice;
        require(stakedBalances[agent] >= reimbursement, "Insufficient stake for gas");

        stakedBalances[agent] -= reimbursement;
        (bool reimbursed, ) = msg.sender.call{value: reimbursement}("");
        require(reimbursed, "Reimbursement failed");

        bytes4 selector = _functionSelector(callData);
        emit RelayedExecution(msg.sender, agent, selector, reimbursement);
        return returnData;
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
        address actor = _taskActor();
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

    function completeTask(uint256 taskId, bytes calldata result) external {
        address actor = _taskActor();
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

    function _taskActor() internal view returns (address) {
        if (msg.sender == address(this)) {
            require(_relayActive, "Relay context missing");
            return _relayedAgent;
        }
        return msg.sender;
    }

    function _toEthSignedMessageHash(bytes32 hash) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", hash));
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

        if (v < 27) {
            v += 27;
        }
        require(v == 27 || v == 28, "Invalid signature v");

        return ecrecover(digest, v, r, s);
    }

    function _functionSelector(bytes calldata data) internal pure returns (bytes4 selector) {
        assembly {
            selector := calldataload(data.offset)
        }
    }
}
