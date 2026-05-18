// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title AgentRegistry with Batch Operations
/// @notice Gas-efficient batch registration for platforms onboarding many agents
/// @custom:contributor-info agent:QClaw date:2026-05-18 platform-init:[withheld] runtime:Windows_NT x86_64

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
    event BatchRegistered(address indexed owner, uint256 count, uint256 totalFee);

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

    /// @notice Register up to 50 agents in a single transaction
    /// @param names Array of agent names (max 50)
    /// @param endpoints Array of agent endpoints (must match names length)
    /// @return agentIdList Array of created agent IDs
    function batchRegister(
        string[] calldata names,
        string[] calldata endpoints
    ) external payable returns (bytes32[] memory) {
        uint256 count = names.length;
        require(count > 0 && count <= 50, "Batch size must be 1-50");
        require(count == endpoints.length, "Array length mismatch");
        require(msg.value >= registrationFee * count, "Insufficient fee for batch");

        bytes32[] memory agentIdList = new bytes32[](count);

        for (uint256 i = 0; i < count; i++) {
            require(bytes(names[i]).length > 0 && bytes(names[i]).length <= 64, "Invalid name in batch");

            bytes32 agentId = keccak256(abi.encodePacked(msg.sender, names[i], block.timestamp, i));

            // Skip if agent already exists (allow partial batch success)
            if (agents[agentId].registeredAt > 0) {
                agentIdList[i] = bytes32(0);
                continue;
            }

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

            emit AgentRegistered(agentId, msg.sender, names[i]);
            agentIdList[i] = agentId;
        }

        // Refund excess fee
        uint256 totalFee = registrationFee * count;
        if (msg.value > totalFee) {
            (bool success, ) = msg.sender.call{value: msg.value - totalFee}("");
            require(success, "Refund failed");
        }

        emit BatchRegistered(msg.sender, count, totalFee);
        return agentIdList;
    }

    /// @notice Deactivate multiple agents in a single transaction
    /// @param agentIds_ Array of agent IDs to deactivate
    function batchDeactivate(bytes32[] calldata agentIds_) external {
        require(agentIds_.length > 0 && agentIds_.length <= 50, "Batch size must be 1-50");

        for (uint256 i = 0; i < agentIds_.length; i++) {
            if (agents[agentIds_[i]].owner == msg.sender && agents[agentIds_[i]].active) {
                agents[agentIds_[i]].active = false;
                emit AgentDeactivated(agentIds_[i]);
            }
        }
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
