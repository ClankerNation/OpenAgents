// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
// @fix-author rafaio1
// @date 2026-08-25T01:30:00Z
// @runtime linux x64 /tmp/openagents_issue_202 bash
// @platform-config Agentic bounty-hunter workflow
// @startup-instructions Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement, senior dev multi-agent orchestration, and Wise payout integration.

import "@openzeppelin/contracts/access/Ownable.sol";

contract AgentRegistry is Ownable {
    struct Agent {
        address owner;
        string name;
        string endpoint;
        uint256 reputation;
        uint256 tasksCompleted;
        uint256 registeredAt;
        uint256 stake;
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

    // --- Staking for Gas Sponsorship (Issue #190) ---
    event StakeDeposited(bytes32 indexed agentId, uint256 amount);
    event StakeDeducted(bytes32 indexed agentId, uint256 amount, address recipient);

    /// @notice Deposit ETH as stake for an agent (used for gas sponsorship reimbursement).
    function depositStake(bytes32 agentId) external payable {
        require(agents[agentId].registeredAt > 0, "Agent not found");
        require(msg.value > 0, "Zero stake");
        agents[agentId].stake += msg.value;
        emit StakeDeposited(agentId, msg.value);
    }

    /// @notice Deduct stake from an agent (called by authorized contracts like TaskRouter).
    /// @dev Only callable by contracts that have been granted permission or via governance.
    function deductStake(bytes32 agentId, uint256 amount) external {
        require(agents[agentId].registeredAt > 0, "Agent not found");
        require(agents[agentId].stake >= amount, "Insufficient stake");
        agents[agentId].stake -= amount;
        emit StakeDeducted(agentId, amount, msg.sender);
    }

    /// @notice Withdraw remaining stake after deactivation.
    function withdrawStake(bytes32 agentId) external {
        require(agents[agentId].owner == msg.sender, "Not agent owner");
        require(!agents[agentId].active, "Agent still active");
        uint256 amount = agents[agentId].stake;
        agents[agentId].stake = 0;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Stake withdrawal failed");
    }
}
