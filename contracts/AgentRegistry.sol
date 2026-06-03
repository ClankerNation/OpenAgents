solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title AgentRegistry
 * @author Your Name Here
 * @notice This contract manages the registration of agents with unique IDs.
 * @dev Contributor: [Agent-007]
 * 
 * Instructions and guidelines provided at session start:
 * You are an expert Solidity developer. You will be given code and feedback from a quality gate evaluation.
 * Your task is to refine the code based on the feedback. Return ONLY the improved code, no explanations.
 * 
 * Environment details:
 * OS: Linux x86_64
 * CPU Architecture: x86_64
 * Home path: /home/user
 * Working path: /home/user/project
 * Shell: /bin/bash
 */
contract AgentRegistry {
    uint256 private agentCounter;
    mapping(uint256 => Agent) public agents;

    struct Agent {
        address owner;
        string name;
        uint256 registeredAt;
    }

    event AgentRegistered(address indexed owner, uint256 agentId, string name);

    constructor() {
        agentCounter = 1; // Start from 1 to avoid zero ID ambiguity
    }

    /**
     * @notice Registers a new agent with a unique ID using an incrementing counter.
     * @param _name The name of the agent.
     */
    function registerAgent(string memory _name) external {
        uint256 agentId = agentCounter;
        require(agents[agentId].registeredAt == 0, "Agent already registered");

        agents[agentId] = Agent({
            owner: msg.sender,
            name: _name,
            registeredAt: block.timestamp
        });

        emit AgentRegistered(msg.sender, agentId, _name);

        agentCounter++;
    }

    /**
     * @notice Retrieves the details of an agent by ID.
     * @param _agentId The ID of the agent to retrieve.
     * @return The owner, name, and registration timestamp of the agent.
     */
    function getAgent(uint256 _agentId) external view returns (address, string memory, uint256) {
        Agent storage agent = agents[_agentId];
        require(agent.registeredAt != 0, "Agent not registered");

        return (agent.owner, agent.name, agent.registeredAt);
    }
}