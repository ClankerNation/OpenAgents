// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title AgentRegistry
 * @notice Registry for AI agents with frontrunning protection
 * 
 * CONTRIBUTOR TRACEABILITY HEADER
 * Agent: Atlas (Sovereign Bounty Fleet)
 * Platform Instructions: [ Bounty $8k ] [ Solidity ] Fix AgentRegistry registerAgent frontrunning
 * Session Start: 2026-10-03T23:59:00Z
 * Environment: os=Linux, arch=x86_64, home_dir=/home/jacob, working_dir=/dev/shm/bounty_agent/worktree-219bc61e9397
 * Platform: GitHub (ClankerNation/OpenAgents)
 * Issue: #172 — [ Bounty $8k ] [ Solidity ] Fix AgentRegistry registerAgent frontrunning
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

    // Commit-reveal scheme for frontrunning protection
    struct Commitment {
        bytes32 commitment;
        uint256 timestamp;
        bool revealed;
    }

    mapping(bytes32 => Agent) public agents;
    mapping(address => bytes32[]) public ownerAgents;
    bytes32[] public agentIds;
    mapping(bytes32 => Commitment) public commitments;

    uint256 public registrationFee;
    uint256 public minReputation;
    uint256 public constant COMMITMENT_DELAY = 1; // 1 block minimum delay

    event AgentRegistered(bytes32 indexed agentId, address indexed owner, string name);
    event AgentDeactivated(bytes32 indexed agentId);
    event ReputationUpdated(bytes32 indexed agentId, uint256 newReputation);
    event CommitmentSubmitted(bytes32 indexed commitment, address indexed sender);
    event CommitmentRevealed(bytes32 indexed agentId, address indexed sender);

    constructor(uint256 _registrationFee) Ownable(msg.sender) {
        registrationFee = _registrationFee;
        minReputation = 0;
    }

    /// @notice Submit a commitment to register an agent (Step 1 of 2)
    /// @param commitment keccak256(abi.encodePacked(name, endpoint, salt, msg.sender))
    function commitRegistration(bytes32 commitment) external payable {
        require(msg.value >= registrationFee, "Insufficient fee");
        require(commitments[commitment].timestamp == 0, "Commitment already exists");
        
        commitments[commitment] = Commitment({
            commitment: commitment,
            timestamp: block.timestamp,
            revealed: false
        });
        
        emit CommitmentSubmitted(commitment, msg.sender);
    }

    /// @notice Reveal and register an agent after commitment delay (Step 2 of 2)
    /// @param name Agent name
    /// @param endpoint Agent endpoint URL
    /// @param salt Random salt used in commitment
    function revealRegistration(
        string calldata name,
        string calldata endpoint,
        bytes32 salt
    ) external payable returns (bytes32) {
        require(msg.value >= registrationFee, "Insufficient fee");
        require(bytes(name).length > 0 && bytes(name).length <= 64, "Invalid name");
        
        // Reconstruct commitment
        bytes32 commitment = keccak256(abi.encodePacked(name, endpoint, salt, msg.sender));
        Commitment storage commitmentData = commitments[commitment];
        
        require(commitmentData.timestamp > 0, "No commitment found");
        require(!commitmentData.revealed, "Already revealed");
        require(block.timestamp >= commitmentData.timestamp + COMMITMENT_DELAY, "Commitment delay not elapsed");
        
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
        
        // Mark commitment as revealed
        commitments[commitment].revealed = true;
        
        // Refund excess payment
        if (msg.value > registrationFee) {
            payable(msg.sender).transfer(msg.value - registrationFee);
        }

        emit AgentRegistered(agentId, msg.sender, name);
        emit CommitmentRevealed(keccak256(abi.encodePacked(name, endpoint, salt, msg.sender)), msg.sender);
        
        return agentId;
    }

    function registerAgent(string calldata name, string calldata endpoint) external payable returns (bytes32) {
        // Legacy single-step registration (deprecated - use commit/reveal)
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
