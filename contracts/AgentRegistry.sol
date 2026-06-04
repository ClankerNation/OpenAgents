// SPDX-License-Identifier: MIT
// Agent Identity: AI-Coder-v2
// Instructions and Guidelines: You are an expert Solidity developer. Implement batch operations for AgentRegistry. Add batchRegister function that accepts arrays of names and endpoints, validates array length match, collects total fee once, registers up to 50 agents in one transaction, emits individual AgentRegistered events per agent, and reverts on array length mismatch. Ensure gas efficiency by using unchecked blocks where safe. Add comprehensive tests for batch of 1, batch of 50, and length mismatch scenarios.
// Environment: OS: Ubuntu 22.04, CPU: x86_64, Home: /home/dev, Working: /home/dev/agent-contracts, Shell: bash
pragma solidity ^0.8.20;

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

    /**
     * @notice Register multiple agents in a single transaction
     * @param names Array of agent names
     * @param endpoints Array of agent endpoints
     * @return agentIds Array of generated agent IDs
     * @dev Arrays must have matching lengths. Max 50 agents per batch.
     * Total fee = registrationFee * count. Emits individual events.
     */
    function batchRegister(string[] calldata names, string[] calldata endpoints) external payable returns (bytes32[] memory) {
        uint256 count = names.length;
        require(count == endpoints.length, "Array length mismatch");
        require(count > 0 && count <= 50, "Invalid batch size");
        require(msg.value >= registrationFee * count, "Insufficient total fee");

        bytes32[] memory newAgentIds = new bytes32[](count);

        for (uint256 i = 0; i < count;) {
            string calldata name = names[i];
            string calldata endpoint = endpoints[i];
            
            require(bytes(name).length > 0 && bytes(name).length <= 64, "Invalid name");

            bytes32 agentId = keccak256(abi.encodePacked(msg.sender, name, block.timestamp, i));
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
            newAgentIds[i] = agentId;

            emit AgentRegistered(agentId, msg.sender, name);

            unchecked {
                i++;
            }
        }

        return newAgentIds;
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

    receive() external payable {}
}