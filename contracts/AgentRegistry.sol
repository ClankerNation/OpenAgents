// SPDX-License-Identifier: MIT
// Contributor: Feltchy
// Platform: OpenClaw Gateway — agent=main, channel=whatsapp, model=deepseek-v4-pro
// Runtime: Linux 6.6.114.1-microsoft-standard-WSL2 (x64), node=v22.22.2, bash
// Workspace: /home/owner/.openclaw/workspace
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
    uint256 public nextAgentId = 1;

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

        bytes32 agentId = bytes32(uint256(nextAgentId++));

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
     * @notice Register multiple agents in a single transaction.
     * @dev Batch registers up to 50 agents. Total fee = registrationFee * count.
     *      Emits individual AgentRegistered events per registration.
     * @param names     Array of agent names (1-64 chars each, max 50 entries)
     * @param endpoints Array of agent endpoints (must match names length)
     * @return agentIds Array of generated agent IDs in registration order
     */
    function batchRegister(
        string[] calldata names,
        string[] calldata endpoints
    ) external payable returns (bytes32[] memory) {
        uint256 count = names.length;
        require(count > 0 && count <= 50, "Batch size must be 1-50");
        require(count == endpoints.length, "Array length mismatch");
        require(msg.value >= registrationFee * count, "Insufficient total fee");

        bytes32[] memory ids = new bytes32[](count);

        for (uint256 i = 0; i < count; i++) {
            require(bytes(names[i]).length > 0 && bytes(names[i]).length <= 64, "Invalid name in batch");

            bytes32 agentId = bytes32(uint256(nextAgentId++));

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
            ids[i] = agentId;

            emit AgentRegistered(agentId, msg.sender, names[i]);
        }

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
