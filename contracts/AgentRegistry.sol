// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

/// @contributor hermes-agent-deepseek-v4-pro
/// @platform-config User goal: Generate $5+ from GitHub bounties. Session configured for Feishu messaging. Using GitHub PAT token with full repo access.
/// @env os=linux, arch=x64, home_dir=/root, working_dir=/root/hermes-agent, shell=bash
/// @timestamp 2026-05-17T23:00:00Z
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
    uint256 public constant MAX_BATCH_SIZE = 50;

    event AgentRegistered(bytes32 indexed agentId, address indexed owner, string name);
    event AgentDeactivated(bytes32 indexed agentId);
    event ReputationUpdated(bytes32 indexed agentId, uint256 newReputation);
    event BatchRegistered(uint256 count, uint256 totalFee);

    constructor(uint256 _registrationFee) Ownable(msg.sender) {
        registrationFee = _registrationFee;
        minReputation = 0;
    }

    function registerAgent(string calldata name, string calldata endpoint) external payable returns (bytes32) {
        require(msg.value >= registrationFee, "Insufficient fee");
        require(bytes(name).length > 0 && bytes(name).length <= 64, "Invalid name");
        bytes32 agentId = keccak256(abi.encodePacked(msg.sender, name, block.timestamp));
        require(agents[agentId].registeredAt == 0, "Agent exists");
        agents[agentId] = Agent({owner: msg.sender, name: name, endpoint: endpoint, reputation: 100, tasksCompleted: 0, registeredAt: block.timestamp, active: true});
        ownerAgents[msg.sender].push(agentId);
        agentIds.push(agentId);
        emit AgentRegistered(agentId, msg.sender, name);
        return agentId;
    }

    function batchRegister(string[] calldata names, string[] calldata endpoints) external payable returns (bytes32[] memory) {
        require(names.length == endpoints.length, "Array length mismatch");
        require(names.length > 0, "Empty batch");
        require(names.length <= MAX_BATCH_SIZE, "Batch too large");
        uint256 totalFee = registrationFee * names.length;
        require(msg.value >= totalFee, "Insufficient fee");

        bytes32[] memory ids = new bytes32[](names.length);
        for (uint256 i = 0; i < names.length; i++) {
            require(bytes(names[i]).length > 0 && bytes(names[i]).length <= 64, "Invalid name");
            bytes32 agentId = keccak256(abi.encodePacked(msg.sender, names[i], block.timestamp, i));
            require(agents[agentId].registeredAt == 0, "Agent exists");
            agents[agentId] = Agent({owner: msg.sender, name: names[i], endpoint: endpoints[i], reputation: 100, tasksCompleted: 0, registeredAt: block.timestamp, active: true});
            ownerAgents[msg.sender].push(agentId);
            agentIds.push(agentId);
            ids[i] = agentId;
            emit AgentRegistered(agentId, msg.sender, names[i]);
        }
        emit BatchRegistered(names.length, totalFee);
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
        if (delta > 0) { agent.reputation += uint256(delta); }
        else { uint256 decrease = uint256(-delta); agent.reputation = agent.reputation > decrease ? agent.reputation - decrease : 0; }
        emit ReputationUpdated(agentId, agent.reputation);
    }

    function getAgent(bytes32 agentId) external view returns (Agent memory) { return agents[agentId]; }

    function getActiveAgentCount() external view returns (uint256 count) {
        for (uint256 i = 0; i < agentIds.length; i++) { if (agents[agentIds[i]].active) count++; }
    }

    function setRegistrationFee(uint256 _fee) external onlyOwner { registrationFee = _fee; }

    function withdrawFees() external onlyOwner {
        (bool success, ) = owner().call{value: address(this).balance}("");
        require(success, "Withdraw failed");
    }
}
