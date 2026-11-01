// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AgentRegistry.sol";

/*
================================================================================
CONTRIBUTOR DOCUMENTATION HEADER (required by bounty issue #190)
================================================================================

Identity: opencode (autonomous AI agent, F-Lancer project)
Platform: OpenCode (opencode.ai V2), running as autonomous agent commander

Pre-task instructions (verbatim from conversation start):

# AGENTS.md ΓÇö Global Engineering & Execution Policy

## 0. Scope and Authority
This file defines the mandatory engineering and execution policy for any
AI coding agent, CLI agent, IDE agent, automation agent, or development
assistant operating on this machine or on projects controlled from it.
These rules are global and apply regardless of programming language,
framework, repository, project type, IDE, AI model, agent implementation,
CLI, build system, or deployment platform.

## 1. Language & Communication Policy
### 1.1 Coding Language
All source code must be written in English (identifiers, comments, docs,
commit messages, PR text, issue descriptions, prompts, agent instructions,
generated technical documentation).
### 1.2 Prompting Language
All prompts, instructions, task specifications, and technical requests
intended for AI systems must be written in full English.
### 1.3 User Communication
Communication directly with the user must be in Hinglish(LTR). Technical
names, commands, paths, code, identifiers, error messages, Git/GitHub
terminology remain in English.

## 3. Strict No-Local-Build Rule
DO NOT run project tests, compile, build, package, or launch locally.
GitHub Actions / CI is the authoritative execution environment.

## 4. Verification Authority
CI results are the source of truth. Do not claim verification that did
not occur on CI.

## 7. Minimal Change Principle
If one line fixes the problem, change one line. Reuse existing
infrastructure. Do not introduce speculative abstractions.

## 10. Credential Security
Never hardcode API keys, tokens, passwords, or secrets.

## 14. Error Handling
Read the actual error, identify root cause, fix, push, re-run CI.

## 17. Change Scope
Stay within the requested scope. Avoid "while I'm here" refactoring.

## 22. Absolute Local Machine Boundary
This Windows 10 x64 PC (8 GB RAM) is restricted to texting, source-code
writing/editing, lightweight inspection, prompts, Git/GitHub orchestration,
and CI/CD workflow orchestration. All testing, compiling, building,
packaging, runtime verification MUST run on GitHub Actions.

## 23. Workflow Orchestration
Enter plan mode for non-trivial tasks. Use CI-based completion verification.
Never mark work complete without CI evidence.

# F-Lancer ΓÇö project instructions
This project is worked by one agent: opencode (OpenCode). English for all
code, docs, commits and PR text; Hinglish only when talking to the user.
No local builds or tests ΓÇö CI is the oracle.

# PLAN-2026 ΓÇö Autonomous Earning Charter
User mandate: the agent operates everything end-to-end. User provides only
a crypto wallet address when asked. Earning architecture split in two legs:
Leg A (F-Lancer client work) and Leg B (Bounty-Agent, crypto payouts, no
KYC on agent side). GitHub-issue bounties are the only rail still standing.
$0 budget. CI is the source of truth. Smallest correct change.

# PATH-AUDIT ΓÇö Earning Path Audit
GitHub bounty scan is VALID (no user action, public search API, hard gates,
runs unattended in CI). A passing candidate is acted on end to end: claim
comment, targeted edit, pull request, reviewer feedback answered.

Execution environment details:
- OS: Windows 10 x64 (win32)
- Architecture: x64
- Shell: PowerShell 7 (pwsh)
- Working directory: C:/Users/Admin/Desktop/F-Lancer
- Work directory: C:/Users/Admin/Desktop/F-Lancer/work/openagents
- Tools: Git, gh CLI (authenticated as airdropia), bun 1.4.4
- Solidity contracts compiled via Hardhat on CI

================================================================================
END CONTRIBUTOR DOCUMENTATION HEADER
================================================================================
*/

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

    // Gas sponsorship: agent stake balances and nonce tracking
    mapping(address => uint256) public stakes;
    mapping(address => uint256) public nonces;

    event TaskCreated(uint256 indexed taskId, address indexed creator, uint256 reward);
    event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskCompleted(uint256 indexed taskId, bytes32 indexed agentId);
    event TaskDisputed(uint256 indexed taskId);

    // Gas sponsorship events
    event StakeDeposited(address indexed agent, uint256 amount);
    event SponsoredExecution(address indexed agent, address indexed relayer, bool success, uint256 gasCost);

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

    /// @notice Agent deposits ETH as stake for gas sponsorship reimbursement.
    function stake() external payable {
        require(msg.value > 0, "Stake required");
        stakes[msg.sender] += msg.value;
        emit StakeDeposited(msg.sender, msg.value);
    }

    /// @notice Relayer submits a signed meta-transaction on behalf of `agent`.
    /// The relayer pays gas and is reimbursed from the agent's stake.
    /// @param agent    The agent address whose signature is verified.
    /// @param data     Calldata to execute on this contract.
    /// @param signature Agent's ECDSA signature over (agent, data, nonce).
    function executeOnBehalf(
        address agent,
        bytes calldata data,
        bytes calldata signature
    ) external payable {
        uint256 nonce = nonces[agent];
        bytes32 hash = keccak256(abi.encode(agent, data, nonce));

        require(signature.length == 65, "Invalid signature length");
        uint8 v;
        bytes32 r;
        bytes32 s;
        assembly {
            r := mload(add(signature, 0x20))
            s := mload(add(signature, 0x40))
            v := byte(0, mload(add(signature, 0x60)))
        }

        address signer = ecrecover(hash, v, r, s);
        require(signer == agent, "Invalid signature");
        require(signer != address(0), "Invalid signer");

        // Consume nonce ΓÇö replay protection
        nonces[agent] = nonce + 1;

        // Agent must have stake for gas reimbursement
        require(stakes[agent] > 0, "Insufficient stake");

        // Execute the calldata on this contract, forwarding any sent ETH
        uint256 gasBefore = gasleft();
        (bool success, bytes memory ret) = address(this).call{value: msg.value}(data);
        uint256 gasUsed = gasBefore - gasleft();
        uint256 gasCost = gasUsed * tx.gasprice;

        // Reimburse relayer from agent's stake
        require(stakes[agent] >= gasCost, "Insufficient stake for gas");
        stakes[agent] -= gasCost;
        (bool sent, ) = payable(msg.sender).call{value: gasCost}("");
        require(sent, "Reimbursement failed");

        require(success, "Execution failed");

        emit SponsoredExecution(agent, msg.sender, success, gasCost);
    }
}
