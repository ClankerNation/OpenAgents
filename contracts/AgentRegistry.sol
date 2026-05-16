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
 * Task: Fix AgentRegistry per issue #194 — add batchRegister for gas-efficient
 *       multi-agent registration in a single transaction.
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

    /// @notice Maximum number of agents that can be registered in a single batch call
    uint256 public constant MAX_BATCH_SIZE = 50;

    event AgentRegistered(bytes32 indexed agentId, address indexed owner, string name);
    event AgentDeactivated(bytes32 indexed agentId);
    event ReputationUpdated(bytes32 indexed agentId, uint256 newReputation);

    constructor(uint256 _registrationFee) Ownable(msg.sender) {
        registrationFee = _registrationFee;
        minReputation = 0;
    }

    /// @notice Register a single agent.
    /// @param name Agent display name (1-64 chars).
    /// @param endpoint Agent API endpoint URL.
    /// @return agentId Unique identifier for the registered agent.
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

    /// @notice Batch register multiple agents in a single transaction.
    /// @dev Up to MAX_BATCH_SIZE (50) agents per call. Total fee = registrationFee * count.
    ///      Each agent gets a unique ID and individual event emission.
    /// @param names Array of agent names (1-64 chars each).
    /// @param endpoints Array of agent endpoint URLs. Must match names length.
    /// @return agentIds Array of unique agent IDs, one per registered agent.
    function batchRegister(string[] calldata names, string[] calldata endpoints)
        external
        payable
        returns (bytes32[] memory)
    {
        uint256 count = names.length;
        require(count == endpoints.length, "Array length mismatch");
        require(count > 0, "Empty batch");
        require(count <= MAX_BATCH_SIZE, "Batch too large");
        require(msg.value >= registrationFee * count, "Insufficient fee");

        bytes32[] memory ids = new bytes32[](count);

        for (uint256 i = 0; i < count; i++) {
            require(bytes(names[i]).length > 0 && bytes(names[i]).length <= 64, "Invalid name");

            bytes32 agentId = keccak256(abi.encodePacked(msg.sender, names[i], block.timestamp, i));

            require(agents[agentId].registeredAt == 0, "Agent exists");

            agents[agentId] = Agent({
                owner: msg.sender,
                name: names[i],
                endpoint: endpoints[i],
                reputation: 100,
                tasksCompleted: 0,
                registeredAt: block.timestamp,
                active: true
            });

            ownerAgents[msg.sender].push(agentId);
            agentIds.push(agentId);
            ids[i] = agentId;

            emit AgentRegistered(agentId, msg.sender, names[i]);
        }

        return ids;
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
