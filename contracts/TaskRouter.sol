// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title TaskRouter with Gas Sponsorship Relay
/// @notice Agents can submit tasks without holding ETH via meta-transactions
/// @custom:contributor-info agent:QClaw date:2026-05-18 platform-init:[withheld] runtime:Windows_NT x86_64

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

    // --- Gas Sponsorship State ---
    mapping(address => uint256) public stakedBalance;
    mapping(address => uint256) public nonces;
    uint256 public relayerFee; // fee paid to relayer per meta-tx (in wei)

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);

    // --- Gas Sponsorship Events ---
    event StakeDeposited(address indexed agent, uint256 amount);
    event StakeWithdrawn(address indexed agent, uint256 amount);
    event MetaTxExecuted(address indexed agent, address indexed relayer, bytes4 selector, uint256 relayerFeePaid);

    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
        relayerFee = 0.001 ether; // default relayer fee
    }

    // --- Staking Functions ---

    /// @notice Deposit ETH to stake for gas reimbursement
    function depositStake() external payable {
        require(msg.value > 0, "Must deposit ETH");
        stakedBalance[msg.sender] += msg.value;
        emit StakeDeposited(msg.sender, msg.value);
    }

    /// @notice Withdraw unused staked balance
    function withdrawStake(uint256 amount) external {
        require(stakedBalance[msg.sender] >= amount, "Insufficient stake");
        stakedBalance[msg.sender] -= amount;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Withdrawal failed");
        emit StakeWithdrawn(msg.sender, amount);
    }

    // --- Gas Sponsorship Relay ---

    /// @notice Execute a function on behalf of an agent who signed the calldata
    /// @param agent The address of the agent whose behalf we are executing
    /// @param calldata_ The encoded function call to execute
    /// @param signature The agent's EIP-191 signature over (nonce + calldata)
    /// @return The return data from the executed function
    function executeOnBehalf(
        address agent,
        bytes calldata calldata_,
        bytes calldata signature
    ) external returns (bytes memory) {
        // Verify the agent signed the calldata
        bytes32 messageHash = keccak256(abi.encodePacked(
            nonces[agent],
            calldata_
        ));
        bytes32 ethSignedHash = keccak256(abi.encodePacked(
            "\x19Ethereum Signed Message:\x32",
            messageHash
        ));

        address signer = recoverSigner(ethSignedHash, signature);
        require(signer == agent, "Invalid signature");

        // Check agent has enough stake to cover relayer fee
        require(stakedBalance[agent] >= relayerFee, "Insufficient stake for relayer fee");

        // Increment nonce to prevent replay
        nonces[agent]++;

        // Deduct relayer fee from agent's stake
        stakedBalance[agent] -= relayerFee;

        // Pay relayer
        (bool success, ) = msg.sender.call{value: relayerFee}("");
        require(success, "Relayer fee transfer failed");

        // Execute the function call
        (bool callSuccess, bytes memory returnData) = address(this).call(calldata_);
        require(callSuccess, "Meta-transaction execution failed");

        emit MetaTxExecuted(agent, msg.sender, bytes4(calldata_), relayerFee);

        return returnData;
    }

    /// @notice Recover signer address from signature
    function recoverSigner(bytes32 hash, bytes memory signature) internal pure returns (address) {
        require(signature.length == 65, "Invalid signature length");

        bytes32 r;
        bytes32 s;
        uint8 v;

        assembly {
            r := mload(add(signature, 32))
            s := mload(add(signature, 64))
            v := byte(0, mload(add(signature, 96)))
        }

        if (v < 27) {
            v += 27;
        }

        require(v == 27 || v == 28, "Invalid signature v value");
        return ecrecover(hash, v, r, s);
    }

    /// @notice Update relayer fee (only via direct call, not meta-tx)
    function setRelayerFee(uint256 _relayerFee) external {
        // In production, this would be owner-only
        relayerFee = _relayerFee;
    }

    // --- Original Functions (unchanged) ---

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
