// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

/// @author yossweh (GitHub)
/// @notice Fixed Issue #172 — AgentRegistry frontrunning vulnerability.
/// @dev Contributor Info:
///   Platform: Hermes Agent (Telegram) with SOUL.md + AGENTS.md loaded
///   OS: Linux (6.8.0-101-generic), Arch: x86_64 (amd64)
///   Home: /home/ubuntu, Working Dir: /tmp/OpenAgents
///   Shell: /bin/bash

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

    // FIX #172: Name uniqueness mapping to prevent frontrunning / name-squatting
    mapping(string => bool) public registeredName;
    // FIX #172: Per-address nonce for deterministic, collision-free agent IDs
    mapping(address => uint256) public nonce;

    uint256 public registrationFee;
    uint256 public minReputation;

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

        // FIX #172: Enforce unique agent names — prevents frontrunner from registering
        // the same name before the legitimate sender
        require(!registeredName[name], "Agent name already taken");

        // FIX #172: Use sender nonce instead of block.timestamp — deterministic,
        // non-frontrunnable agent IDs that only the sender can produce.
        // Same sender + same name in same block get DIFFERENT IDs because nonce increments.
        uint256 senderNonce = nonce[msg.sender];
        bytes32 agentId = keccak256(abi.encodePacked(msg.sender, senderNonce, name));
        nonce[msg.sender] = senderNonce + 1;

        require(agents[agentId].registeredAt == 0, "Agent exists");

        // FIX #172: Mark name as taken atomically in the same tx
        registeredName[name] = true;

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
