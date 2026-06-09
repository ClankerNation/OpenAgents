// SPDX-License-Identifier: MIT
// Agent Identity: Qwen Code via AIGON Enterprise (orchestrator: aigon-orchestrator)
// Instructions and Guidelines (verbatim): You are Qwen Code in WAR MODE.
//   System Law Omega active (L1-L11 + C1-C8). 20 Quality Gates mandatory.
//   Task: Add batchRegister(string[] names, string[] endpoints) to AgentRegistry.sol
//     for ClankerNation/OpenAgents bounty #194 ($4,000).
//   Requirements: Single tx up to 50 agents, individual AgentRegistered events per agent,
//     collect total fee once (registrationFee * count), revert on array length mismatch,
//     gas efficient (unchecked loops), backwards compatible (existing single register unchanged),
//     comprehensive tests (batch of 1, batch of 50, length mismatch).
//   PR title: "fix: add batch operations to AgentRegistry"
//   PR body must end with: "Fixes #194\n\n---\n_PR by Szamani AI_"
// Environment: OS: Linux, CPU: x86_64, Home: /root, Working: /tmp/OpenAgents, Shell: /bin/bash
pragma solidity ^0.8.24;

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
     * @notice Register multiple agents in a single transaction for gas efficiency
     * @param names Array of agent names (must match endpoints length)
     * @param endpoints Array of agent endpoints (must match names length)
     * @return result Array of generated agent IDs for all registered agents
     * @dev Arrays must have equal length (non-zero, max 50). Total fee = registrationFee * count.
     *      Emits individual AgentRegistered events per agent. Storage tracking arrays updated.
     */
    function batchRegister(string[] calldata names, string[] calldata endpoints)
        external
        payable
        returns (bytes32[] memory)
    {
        uint256 count = names.length;
        require(count == endpoints.length, "Array length mismatch");
        require(count > 0 && count <= 50, "Invalid batch size");
        require(msg.value >= registrationFee * count, "Insufficient total fee");

        bytes32[] memory result = new bytes32[](count);

        for (uint256 i = 0; i < count;) {
            string calldata name = names[i];
            string calldata endpoint = endpoints[i];

            require(bytes(name).length > 0 && bytes(name).length <= 64, "Invalid name at index");

            bytes32 agentId = keccak256(abi.encodePacked(msg.sender, name, block.timestamp, i));
            require(agents[agentId].registeredAt == 0, "Agent exists at index");

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
            result[i] = agentId;
            agentIds.push(agentId);

            emit AgentRegistered(agentId, msg.sender, name);

            unchecked {
                i++;
            }
        }

        return result;
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
