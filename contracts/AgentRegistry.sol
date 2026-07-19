// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

/// @contributor-info {
///   "name": "ahmedabdelkarim504-commits",
///   "platform_instructions": "Agent protocol: Read Brain Home.md first. Read E:\\AiLab\\Obsidian Vault\\Brain Home.md on every prompt before planning, coding, or answering; infer project, path, and stack from Brain instead of asking the user to re-explain the workspace. NEVER DELETE ANYTHING WITHOUT EXPLICIT USER PERMISSION. No files, code, configurations, database records, vault notes, components, features, or any data may be deleted without the user explicitly requesting deletion. Always ask for confirmation before deleting. Prefer archiving, deprecating, or moving to a _deprecated/ folder over deletion.",
///   "runtime": {
///     "os": "win32",
///     "arch": "x64",
///     "home_dir": "C:\\Users\\SS",
///     "working_dir": "E:\\AiLab",
///     "shell": "powershell.exe"
///   },
///   "timestamp": "2026-07-17T15:10:00Z"
/// }
/// @title AgentRegistry
/// @notice Registry for AI agents with reputation tracking.
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

    /// @notice Batch register multiple agents in a single transaction.
    /// @param names Array of agent names (max 50).
    /// @param endpoints Array of agent endpoints (max 50).
    /// @return agentIds Array of registered agent IDs.
    function batchRegister(
        string[] calldata names,
        string[] calldata endpoints
    ) external payable returns (bytes32[] memory) {
        require(names.length == endpoints.length, "Array length mismatch");
        require(names.length > 0 && names.length <= 50, "Batch size must be 1-50");

        uint256 totalFee = registrationFee * names.length;
        require(msg.value >= totalFee, "Insufficient total fee");

        bytes32[] memory ids = new bytes32[](names.length);

        for (uint256 i = 0; i < names.length; i++) {
            require(bytes(names[i]).length > 0 && bytes(names[i]).length <= 64, "Invalid name");

            bytes32 agentId = keccak256(abi.encodePacked(msg.sender, names[i], block.timestamp + i));
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
