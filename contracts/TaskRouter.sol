// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";

contract TaskRouter {
    AgentRegistry public registry;
    uint256 private constant MIN_GAS_OVERHEAD = 40_000;
    uint256 private constant SECP256K1N_HALF =
        0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0;

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
    mapping(address => uint256) public gasStake;
    mapping(address => uint256) public nonces;
    address private _relayedSender;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event GasStakeDeposited(address indexed agent, uint256 amount);
    event GasStakeWithdrawn(address indexed agent, uint256 amount);
    event RelayedExecution(address indexed relayer, address indexed agent, uint256 nonce, uint256 reimbursement);

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
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Assigned, "Not assigned");

        AgentRegistry.Agent memory agent = registry.getAgent(task.assignedAgent);
        require(agent.owner == _msgSender(), "Not assigned agent owner");

        task.result = result;
        task.status = TaskStatus.Completed;

        uint256 fee = task.reward * platformFee / 10000;
        uint256 payout = task.reward - fee;

        (bool success, ) = _msgSender().call{value: payout}("");
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

    function stakeForGas() external payable {
        require(msg.value > 0, "Stake required");
        gasStake[msg.sender] += msg.value;
        emit GasStakeDeposited(msg.sender, msg.value);
    }

    function withdrawGasStake(uint256 amount) external {
        require(amount > 0, "Amount required");
        uint256 currentStake = gasStake[msg.sender];
        require(currentStake >= amount, "Insufficient gas stake");

        gasStake[msg.sender] = currentStake - amount;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Withdraw failed");

        emit GasStakeWithdrawn(msg.sender, amount);
    }

    function executeOnBehalf(address agent, bytes calldata callData, bytes calldata signature) external {
        require(agent != address(0), "Invalid agent");
        require(callData.length >= 4, "Invalid calldata");
        require(_relayedSender == address(0), "Relay in progress");

        bytes4 selector = _selectorFromCalldata(callData);
        require(selector == this.assignTask.selector || selector == this.completeTask.selector, "Relay selector not allowed");

        uint256 nonce = nonces[agent];
        _validateRelaySignature(agent, nonce, callData, signature);

        uint256 gasAtStart = gasleft();
        nonces[agent] = nonce + 1;
        _executeRelayedCall(agent, callData);

        uint256 reimbursement = _reimburseRelayer(agent, gasAtStart);

        emit RelayedExecution(msg.sender, agent, nonce, reimbursement);
    }

    function _msgSender() internal view returns (address) {
        if (msg.sender == address(this) && _relayedSender != address(0)) {
            return _relayedSender;
        }
        return msg.sender;
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

        require(uint256(s) <= SECP256K1N_HALF, "Invalid s");
        require(v == 27 || v == 28, "Invalid v");

        address signer = ecrecover(digest, v, r, s);
        require(signer != address(0), "Invalid signer");
        return signer;
    }

    function _selectorFromCalldata(bytes calldata callData) internal pure returns (bytes4 selector) {
        assembly {
            selector := calldataload(callData.offset)
        }
    }

    function _validateRelaySignature(
        address agent,
        uint256 nonce,
        bytes calldata callData,
        bytes calldata signature
    ) internal view {
        bytes32 digest = keccak256(abi.encodePacked(address(this), block.chainid, agent, nonce, keccak256(callData)));
        bytes32 ethSignedDigest = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", digest));
        address signer = _recoverSigner(ethSignedDigest, signature);
        require(signer == agent, "Invalid signature");
    }

    function _executeRelayedCall(address agent, bytes calldata callData) internal {
        _relayedSender = agent;
        (bool success, bytes memory returnData) = address(this).call(callData);
        _relayedSender = address(0);

        if (!success) {
            _revertWithReason(returnData);
        }
    }

    function _reimburseRelayer(address agent, uint256 gasAtStart) internal returns (uint256 reimbursement) {
        uint256 gasUsed = gasAtStart - gasleft() + MIN_GAS_OVERHEAD;
        reimbursement = gasUsed * tx.gasprice;

        uint256 stakeBalance = gasStake[agent];
        require(stakeBalance >= reimbursement, "Insufficient gas stake");
        gasStake[agent] = stakeBalance - reimbursement;

        (bool paid, ) = msg.sender.call{value: reimbursement}("");
        require(paid, "Relay reimbursement failed");
    }

    function _revertWithReason(bytes memory returnData) private pure {
        if (returnData.length < 68) {
            revert("Relayed call failed");
        }
        assembly {
            returnData := add(returnData, 0x04)
        }
        revert(abi.decode(returnData, (string)));
    }
}
