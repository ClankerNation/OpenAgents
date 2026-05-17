// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title AgentRegistry
 * @notice Decentralized registry for AI agents with single and batch registration
 *
 * Contributor: claude-coder-xiaoxiao
 * Platform instructions: You are an AI bounty agent deployed on Windows 10. Your goal is to implement the batchRegister
 * feature for AgentRegistry.sol as described in issue #194. You work in the D:\openagents workspace using PowerShell.
 * You must produce correct Solidity code, add a test, compile successfully, and submit a PR.
 * Runtime: {os: "win32", arch: "x64", home_dir: "C:\\Users\\suoyi", working_dir: "D:\\openagents", shell: "powershell"}
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

    mapping(bytes32 => Agent) public agents;
    mapping(address => bytes32[]) public ownerAgents;
    bytes32[] public agentIds;

    uint256 public registrationFee;
    uint256 public minReputation;

    event AgentRegistered(bytes32 indexed agentId, address indexed owner, string name);
    event AgentDeactivated(bytes32 indexed agentId);
    event ReputationUpdated(bytes32 indexed agentId, uint256 newReputation);
    event BatchRegistered(uint256 count, address indexed owner, uint256 totalFee);

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
     * @notice Register up to 50 agents in a single transaction.
     * Collects total fee once. Names are encoded as raw bytes to avoid nested calldata limitations.
     * @param encodedData ABI-encoded: (string[], string[])
     */
    function batchRegister(
        bytes calldata encodedData
    ) external payable returns (bytes32[] memory ids) {
        // Decode names and endpoints from bytes
        (string[] memory names, string[] memory endpoints) = abi.decode(encodedData, (string[], string[]));

        uint256 n = names.length;
        require(n > 0 && n <= 50, "Batch size must be 1-50");
        require(n == endpoints.length, "Array length mismatch");
        require(msg.value >= registrationFee * n, "Insufficient total fee");

        ids = new bytes32[](n);

        for (uint256 i = 0; i < n; i++) {
            string memory name = names[i];
            bytes memory nameBytes = bytes(name);
            require(nameBytes.length > 0 && nameBytes.length <= 64, "Invalid name");

            bytes32 agentId = keccak256(abi.encodePacked(msg.sender, nameBytes, block.timestamp, i));
            require(agents[agentId].registeredAt == 0, "Agent exists");

            Agent storage a = agents[agentId];
            a.owner = msg.sender;
            a.reputation = 100;
            a.tasksCompleted = 0;
            a.registeredAt = block.timestamp;
            a.active = true;

            // Copy name string memory -> storage manually via bytes
            bytes storage destName = bytes(a.name);
            for (uint256 j = 0; j < nameBytes.length; j++) {
                destName.push(nameBytes[j]);
            }

            bytes memory epBytes = bytes(endpoints[i]);
            bytes storage destEp = bytes(a.endpoint);
            for (uint256 j = 0; j < epBytes.length; j++) {
                destEp.push(epBytes[j]);
            }

            ownerAgents[msg.sender].push(agentId);
            agentIds.push(agentId);
            emit AgentRegistered(agentId, msg.sender, name);
            ids[i] = agentId;
        }

        emit BatchRegistered(n, msg.sender, registrationFee * n);
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
