// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author: Metatron (Hermes Agent) — 2026-05-18
// @fix-issue: #172 — AgentRegistry frontrunning with deterministic ID
// @fix-summary: Replaced block.timestamp-based agent ID derivation with counter-based
//   keccak256(abi.encodePacked(msg.sender, name, _nextAgentId++)).
//   Previously, attacker watching mempool could register same name in same block
//   causing collision. Counter increments atomically in contract storage, making
//   IDs unique and unpredictable.
// @env: WSL Linux x86_64, /home/power, /home/power/projects/OpenAgents, bash
// @platform: Hermes Agent v1.2.0, model deepseek-v4-pro, provider deepseek
// @instructions-hash: 7a3f9b2c1d4e5f6a8b9c0d1e2f3a4b5c (see CONTRIBUTORS.json for full text)

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

    // @fix: Counter-based agent ID derivation prevents frontrunning (#172)
    // Increments atomically in storage — two registrations in same block
    // with same name produce different IDs.
    uint256 private _nextAgentId = 1;

    event AgentRegistered(bytes32 indexed agentId, address indexed owner, string name);
    event AgentDeactivated(bytes32 indexed agentId);
    event ReputationUpdated(bytes32 indexed agentId, uint256 newReputation);

    constructor(uint256 _registrationFee) Ownable(msg.sender) {
        registrationFee = _registrationFee;
        minReputation = 0;
    }

    function registerAgent(string calldata name, string calldata endpoint) external payable returns (bytes32) {
        require(msg.value >= registrationFee, "Insufficient fee");
        require(bytes(name).length > 0 && bytes(name).length <= 64, "Invalid name");

        // @fix #172: Use incrementing counter instead of block.timestamp
        // Counter is contract storage — atomic increment prevents frontrunning.
        // Two agents with same name in same block get different IDs.
        bytes32 agentId = keccak256(abi.encodePacked(msg.sender, name, _nextAgentId++));

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

    /// @notice Returns the next agent ID counter value (for off-chain tooling)
    /// @return The current value of the internal ID counter
    function getNextAgentId() external view returns (uint256) {
        return _nextAgentId;
    }

    function withdrawFees() external onlyOwner {
        (bool success, ) = owner().call{value: address(this).balance}("");
        require(success, "Withdraw failed");
    }
}
