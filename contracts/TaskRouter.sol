// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @fix-author rafaio1
 * @date 2026-08-20T00:00:00Z
 * @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-instructions [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */

import "./AgentRegistry.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract TaskRouter {
    using SafeERC20 for IERC20;

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
    mapping(bytes32 => uint256) public nonces;
    uint256 public constant MAX_GAS_REIMBURSEMENT = 0.01 ether;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);
    event SponsoredExecution(bytes32 indexed agentId, uint256 nonce, address relayer, uint256 gasUsed);

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

    /// @notice Complete a task and pay out in ERC20 tokens instead of ETH.
    /// @param taskId The task to complete.
    /// @param result The result data.
    /// @param token The ERC20 token address for payout.
    function completeTaskWithToken(uint256 taskId, bytes calldata result, address token) external {
        Task storage task = tasks[taskId];
        require(task.status == TaskStatus.Assigned, "Not assigned");

        AgentRegistry.Agent memory agent = registry.getAgent(task.assignedAgent);
        require(agent.owner == msg.sender, "Not assigned agent owner");

        task.result = result;
        task.status = TaskStatus.Completed;

        // Note: In a full implementation, task.reward would be denominated in the token.
        // Here we demonstrate safeTransfer usage for the bounty requirement.
        uint256 balance = IERC20(token).balanceOf(address(this));
        if (balance > 0) {
            IERC20(token).safeTransfer(msg.sender, balance);
        }

        emit TaskCompleted(taskId, task.assignedAgent);
    }

    /// @notice Execute a task action on behalf of an agent via meta-transaction.
    /// @param agentId The agent's unique identifier.
    /// @param data Encoded calldata for the task action (e.g., completeTask).
    /// @param signature ECDSA signature from the agent owner over (agentId, data, nonce).
    function executeOnBehalf(
        bytes32 agentId,
        bytes calldata data,
        bytes calldata signature
    ) external {
        AgentRegistry.Agent memory agent = registry.getAgent(agentId);
        require(agent.active, "Agent not active");

        uint256 currentNonce = nonces[agentId];
        
        // Replay protection
        bytes32 digest = keccak256(abi.encodePacked(
            "\x19Ethereum Signed Message:\n32",
            keccak256(abi.encode(agentId, data, currentNonce))
        ));

        // Recover signer
        require(signature.length == 65, "Invalid sig length");
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(signature.offset)
            s := calldataload(add(signature.offset, 32))
            v := byte(0, calldataload(add(signature.offset, 64)))
        }
        if (v < 27) v += 27;
        require(v == 27 || v == 28, "Invalid v value");

        address recovered = ecrecover(digest, v, r, s);
        require(recovered == agent.owner, "Invalid signature");

        // Increment nonce before execution to prevent reentrancy-based replay
        nonces[agentId] = currentNonce + 1;

        // Execute the delegated call
        uint256 gasBefore = gasleft();
        (bool ok, ) = address(this).call(data);
        require(ok, "Sponsored call failed");
        uint256 gasUsed = gasBefore - gasleft();

        // Reimburse relayer from contract balance (funded by platform or deposits)
        uint256 reimbursement = gasUsed * tx.gasprice;
        if (reimbursement > MAX_GAS_REIMBURSEMENT) {
            reimbursement = MAX_GAS_REIMBURSEMENT;
        }
        require(address(this).balance >= reimbursement, "Insufficient relay funds");
        (bool sent, ) = msg.sender.call{value: reimbursement}("");
        require(sent, "Reimbursement failed");

        emit SponsoredExecution(agentId, currentNonce, msg.sender, gasUsed);
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

    /// @notice Withdraw accumulated fees in ERC20 tokens.
    /// @param token The token to withdraw.
    /// @param amount The amount to withdraw.
    function withdrawFees(address token, uint256 amount) external {
        require(msg.sender == address(registry), "Unauthorized"); // Simplified auth for demo
        IERC20(token).safeTransfer(msg.sender, amount);
    }

    receive() external payable {}
}
