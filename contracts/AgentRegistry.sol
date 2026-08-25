// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

// @fix-author rafaio1
// @date 2026-08-25T00:00:00Z
// @runtime linux x64 /tmp/openagents_issue_182 bash
// @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement

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
    event AgentsBatchRegistered(uint256 count, address indexed owner);

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
     * @notice Register multiple agents in a single transaction to reduce gas overhead
     * @dev Implements batch operations per issue #182. Fee must cover all registrations.
     * @param names Array of agent names (each 1-64 chars)
     * @param endpoints Array of agent endpoints corresponding to each name
     */
    function registerAgentsBatch(
        string[] calldata names,
        string[] calldata endpoints
    ) external payable returns (bytes32[] memory newAgentIds) {
        uint256 count = names.length;
        require(count > 0 && count == endpoints.length, "Invalid input lengths");
        require(msg.value >= registrationFee * count, "Insufficient batch fee");

        newAgentIds = new bytes32[](count);

        for (uint256 i = 0; i < count; ) {
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
            newAgentIds[i] = agentId;

            emit AgentRegistered(agentId, msg.sender, names[i]);

            unchecked { ++i; }
        }

        emit AgentsBatchRegistered(count, msg.sender);
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
        for (uint256 i = 0; i < agentIds.length; ) {
            if (agents[agentIds[i]].active) count++;
            unchecked { ++i; }
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
