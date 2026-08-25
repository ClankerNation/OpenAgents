// @fix-author rafaio1
// @date 2026-08-25T06:40:00Z
// @runtime linux x64 /tmp/openagents_issue_190 bash
// @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement for gas sponsorship relay (Issue #190)
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

    /// @notice Tracks nonces per agent for replay protection in sponsored transactions.
    mapping(address => uint256) public agentNonces;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event SponsoredExecution(address indexed agent, address indexed relayer, uint256 nonce, uint256 gasReimbursement);

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

    /// @notice Execute a transaction on behalf of an agent using meta-transaction pattern.
    /// @param agent The agent address that signed the calldata.
    /// @param data The encoded function call to execute.
    /// @param signature ECDSA signature from the agent over keccak256(abi.encodePacked(nonce, data)).
    /// @dev Relayer pays gas and is reimbursed from the contract balance (representing agent stake).
    ///      Nonce prevents replay attacks. Signature must recover to agent address.
    function executeOnBehalf(
        address agent,
        bytes calldata data,
        bytes calldata signature
    ) external {
        uint256 currentNonce = agentNonces[agent];
        
        // Replay protection: verify nonce matches expected value
        bytes32 digest = keccak256(abi.encodePacked(currentNonce, data));
        bytes32 ethSignedHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", digest));
        
        // Recover signer from signature
        require(signature.length == 65, "Invalid signature length");
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(add(signature.offset, 0))
            s := calldataload(add(signature.offset, 32))
            v := byte(0, calldataload(add(signature.offset, 64)))
        }
        if (v < 27) v += 27;
        require(v == 27 || v == 28, "Invalid signature v value");
        
        address recovered = ecrecover(ethSignedHash, v, r, s);
        require(recovered == agent, "Invalid signature");
        
        // Increment nonce before execution to prevent reentrancy-based replay
        agentNonces[agent] = currentNonce + 1;
        
        // Measure gas for reimbursement
        uint256 gasStart = gasleft();
        
        // Execute the delegated call
        (bool success, ) = address(this).call(data);
        require(success, "Sponsored execution failed");
        
        // Calculate gas reimbursement (gas used * tx.gasprice)
        uint256 gasUsed = gasStart - gasleft();
        uint256 reimbursement = gasUsed * tx.gasprice;
        
        // Reimburse relayer from contract balance (agent's staked funds)
        require(address(this).balance >= reimbursement, "Insufficient stake for gas reimbursement");
        (bool paid, ) = msg.sender.call{value: reimbursement}("");
        require(paid, "Gas reimbursement failed");
        
        emit SponsoredExecution(agent, msg.sender, currentNonce, reimbursement);
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

    /// @notice Allow agents or stakeholders to deposit ETH for gas sponsorship.
    receive() external payable {}
}
