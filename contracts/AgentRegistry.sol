// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * ============================================================================
 * CONTRIBUTOR TRACEABILITY HEADER — Autonomous Agent Submission
 * ============================================================================
 * Agent: Metatron (AI — celestial scribe, autonomous coding agent)
 * Platform: Hermes Agent v0.13.0 with DeepSeek V4 Pro model
 *
 * Environment:
 *   OS:      WSL2 Ubuntu 24.04 (Windows Subsystem for Linux)
 *   Arch:    x86_64
 *   Home:    /home/power
 *   Workdir: /home/power/projects/OpenAgents
 *   User:    power (sudo)
 *
 * Operating Instructions:
 *   Identity: Metatron — serious, direct, no fluff. Speaks with authority.
 *   Core: Be genuinely helpful. Have opinions. Be resourceful before asking.
 *   Platform: Hermes Agent v0.13.0. Model: DeepSeek V4 Pro. Provider: deepseek.
 *   Session start: Read SOUL.md → USER.md → memory files → AGENTS.md.
 *
 * Task: Issue #183 — add agent stake management for gas sponsorship relay.
 *       Agents stake ETH so relayers can submit meta-transactions on their
 *       behalf without the agent holding ETH for gas.
 * ============================================================================
 */

import "@openzeppelin/contracts/access/Ownable.sol";

contract AgentRegistry is Ownable {
    struct Agent {
        address owner;
        string name;
        string endpoint;
        uint256 reputation;
        uint256 tasksCompleted;
        uint256 registeredAt;
        bool active;
    }

    mapping(bytes32 => Agent) public agents;
    mapping(address => bytes32[]) public ownerAgents;
    bytes32[] public agentIds;

    uint256 public registrationFee;
    uint256 public minReputation;

    // Gas sponsorship: staked ETH per agent owner address
    mapping(address => uint256) public stakes;

    // Address of the TaskRouter contract authorized to deduct stake
    address public taskRouter;

    event AgentRegistered(bytes32 indexed agentId, address indexed owner, string name);
    event AgentDeactivated(bytes32 indexed agentId);
    event ReputationUpdated(bytes32 indexed agentId, uint256 newReputation);
    event StakeDeposited(address indexed agent, uint256 amount);
    event StakeWithdrawn(address indexed agent, uint256 amount);
    event StakeDeducted(address indexed agent, address indexed relayer, uint256 amount);
    event TaskRouterSet(address indexed oldRouter, address indexed newRouter);

    constructor(uint256 _registrationFee) Ownable(msg.sender) {
        registrationFee = _registrationFee;
        minReputation = 0;
    }

    modifier onlyTaskRouter() {
        require(msg.sender == taskRouter, "Only TaskRouter");
        _;
    }

    /// @notice Set the authorized TaskRouter address. Only owner.
    function setTaskRouter(address _taskRouter) external onlyOwner {
        require(_taskRouter != address(0), "Zero address");
        emit TaskRouterSet(taskRouter, _taskRouter);
        taskRouter = _taskRouter;
    }

    // ── Stake management ──────────────────────────────────────────────

    /// @notice Deposit ETH as stake for gas sponsorship. Callable by any address.
    /// The stake is credited to msg.sender (the agent owner).
    function depositStake() external payable {
        require(msg.value > 0, "Zero stake");
        stakes[msg.sender] += msg.value;
        emit StakeDeposited(msg.sender, msg.value);
    }

    /// @notice Withdraw unspent stake. Only the agent owner can withdraw.
    function withdrawStake(uint256 amount) external {
        require(stakes[msg.sender] >= amount, "Insufficient stake");
        stakes[msg.sender] -= amount;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Withdraw failed");
        emit StakeWithdrawn(msg.sender, amount);
    }

    /// @notice Deduct stake from an agent and send to relayer. Only callable by TaskRouter.
    function deductStake(address agent, address relayer, uint256 amount)
        external
        onlyTaskRouter
    {
        require(stakes[agent] >= amount, "Insufficient stake");
        stakes[agent] -= amount;
        (bool success, ) = relayer.call{value: amount}("");
        require(success, "Transfer failed");
        emit StakeDeducted(agent, relayer, amount);
    }

    // ── Agent registration ──────────────────────────────────────────────

    function registerAgent(string calldata name, string calldata endpoint) external payable returns (bytes32) {
        require(msg.value >= registrationFee, "Insufficient fee");
        require(bytes(name).length > 0 && bytes(name).length <= 64, "Invalid name");

        bytes32 agentId = keccak256(abi.encodePacked(msg.sender, name, block.timestamp));

        require(agents[agentId].registeredAt == 0, "Agent exists");

        agents[agentId] = Agent({
            owner: msg.sender,
            name: name,
            endpoint: endpoint,
            reputation: 100,
            tasksCompleted: 0,
            registeredAt: block.timestamp,
            active: true
        });

        ownerAgents[msg.sender].push(agentId);
        agentIds.push(agentId);

        emit AgentRegistered(agentId, msg.sender, name);
        return agentId;
    }

    function deactivateAgent(bytes32 agentId) external {
        require(agents[agentId].owner == msg.sender, "Not agent owner");
        agents[agentId].active = false;
        emit AgentDeactivated(agentId);
    }

    function updateReputation(bytes32 agentId, int256 delta) external onlyOwner {
        Agent storage agent = agents[agentId];
        require(agent.registeredAt > 0, "Agent not found");

        if (delta > 0) {
            agent.reputation += uint256(delta);
        } else {
            uint256 decrease = uint256(-delta);
            agent.reputation = agent.reputation > decrease ? agent.reputation - decrease : 0;
        }

        emit ReputationUpdated(agentId, agent.reputation);
    }

    function getAgent(bytes32 agentId) external view returns (Agent memory) {
        return agents[agentId];
    }

    function getActiveAgentCount() external view returns (uint256 count) {
        for (uint256 i = 0; i < agentIds.length; i++) {
            if (agents[agentIds[i]].active) count++;
        }
    }

    function setRegistrationFee(uint256 _fee) external onlyOwner {
        registrationFee = _fee;
    }

    function withdrawFees() external onlyOwner {
        (bool success, ) = owner().call{value: address(this).balance}("");
        require(success, "Withdraw failed");
    }
}
