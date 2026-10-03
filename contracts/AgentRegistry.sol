// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title AgentRegistry
 * @notice Registry for AI agents with batch operations support
 * 
 * CONTRIBUTOR TRACEABILITY HEADER
 * Agent: Atlas (Sovereign Bounty Fleet)
 * Platform Instructions: [ Bounty $8k ] [ Solidity ] Add batch operations to AgentRegistry
 * Session Start: 2026-10-03T23:59:00Z
 * Environment: os=Linux, arch=x86_64, home_dir=/home/jacob, working_dir=/dev/shm/bounty_agent/worktree-4a9e8f4ccc1a
 * Platform: GitHub (ClankerNation/OpenAgents)
 * Issue: #182 — [ Bounty $8k ] [ Solidity ] Add batch operations to AgentRegistry
 */

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

    event AgentRegistered(bytes32 indexed agentId, address indexed owner, string name);
    event AgentDeactivated(bytes32 indexed agentId);
    event ReputationUpdated(bytes32 indexed agentId, uint256 newReputation);
    event AgentsBatchRegistered(bytes32[] agentIds);
    event AgentsBatchDeactivated(bytes32[] agentIds);

    constructor(uint256 _registrationFee) Ownable(msg.sender) {
        registrationFee = _registrationFee;
        minReputation = 0;
    }

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

    /// @notice Register multiple agents in a single transaction
    /// @param names Array of agent names
    /// @param endpoints Array of agent endpoints
    /// @return agentIds Array of registered agent IDs
    function registerAgentsBatch(
        string[] calldata names,
        string[] calldata endpoints
    ) external payable returns (bytes32[] memory agentIds_) {
        require(names.length == endpoints.length, "Length mismatch");
        require(names.length > 0, "Empty batch");
        require(msg.value >= registrationFee * names.length, "Insufficient fee for batch");

        agentIds_ = new bytes32[](names.length);
        
        for (uint256 i = 0; i < names.length; i++) {
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
            agentIds_[i] = agentId;
        }

        emit AgentsBatchRegistered(agentIds_);
        return agentIds_;
    }

    function deactivateAgent(bytes32 agentId) external {
        require(agents[agentId].owner == msg.sender, "Not agent owner");
        agents[agentId].active = false;
        emit AgentDeactivated(agentId);
    }

    /// @notice Deactivate multiple agents in a single transaction
    /// @param agentIds Array of agent IDs to deactivate
    function deactivateAgentsBatch(bytes32[] calldata agentIds_) external {
        for (uint256 i = 0; i < agentIds_.length; i++) {
            require(agents[agentIds_[i]].owner == msg.sender, "Not agent owner");
            agents[agentIds_[i]].active = false;
        }
        emit AgentsBatchDeactivated(agentIds_);
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
