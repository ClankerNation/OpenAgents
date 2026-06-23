// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title AgentRegistry — Decentralized AI agent discovery and reputation
/// @notice Register agents, track reputation, manage task assignments
/// @author Gaotax2006
/// @custom:contributor Gaotax2006 — #172 frontrunning protection via salt-based agent IDs
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
    uint256 public nonce;

    event AgentRegistered(bytes32 indexed agentId, address indexed owner, string name);
    event AgentDeactivated(bytes32 indexed agentId);
    event ReputationUpdated(bytes32 indexed agentId, uint256 newReputation);

    constructor(uint256 _registrationFee) Ownable(msg.sender) {
        registrationFee = _registrationFee;
        minReputation = 0;
    }

    function registerAgent(string calldata name, string calldata endpoint) external payable returns (bytes32) {
        return _registerAgent(name, endpoint, bytes32(0));
    }

    /// @notice Register an agent with a salt to prevent frontrunning.
    /// @param name Agent display name.
    /// @param endpoint Agent service endpoint URL.
    /// @param salt User-provided salt for unique ID generation.
    /// @return agentId Unique identifier for the registered agent.
    function registerAgentWithSalt(string calldata name, string calldata endpoint, bytes32 salt)
        external
        payable
        returns (bytes32 agentId)
    {
        require(salt != bytes32(0), "AgentRegistry: salt required");
        return _registerAgent(name, endpoint, salt);
    }

    function _registerAgent(string calldata name, string calldata endpoint, bytes32 salt)
        internal
        returns (bytes32 agentId)
    {
        require(msg.value >= registrationFee, "Insufficient fee");
        require(bytes(name).length > 0 && bytes(name).length <= 64, "Invalid name");

        // Salt-based ID: combines sender, name, salt, and global nonce
        // ensures uniqueness even for same name + same block timestamp
        agentId = keccak256(abi.encodePacked(msg.sender, name, salt, nonce));
        nonce++;

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
