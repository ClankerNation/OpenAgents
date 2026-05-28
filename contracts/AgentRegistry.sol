// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @author yossweh (GitHub)
/// @notice Modified for Issue #183 — EIP-2771 trusted forwarder support.
/// @dev Contributor Info:
///   Platform: Hermes Agent (Telegram) with SOUL.md + AGENTS.md loaded
///   OS: Linux (6.8.0-101-generic), Arch: x86_64 (amd64)
///   Home: /home/ubuntu, Working Dir: /tmp/OpenAgents
///   Shell: /bin/bash

import "@openzeppelin/contracts/access/Ownable.sol";

contract AgentRegistry is Ownable {
    // FIX #183: Trusted gas relay forwarder — enables gasless agent registration
    address public trustedForwarder;

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

    // FIX #172: Name uniqueness mapping to prevent frontrunning / name-squatting
    mapping(string => bool) public registeredName;
    // FIX #172: Per-address nonce for deterministic, collision-free agent IDs
    mapping(address => uint256) public nonce;

    uint256 public registrationFee;
    uint256 public minReputation;

    event AgentRegistered(bytes32 indexed agentId, address indexed owner, string name);
    event AgentDeactivated(bytes32 indexed agentId);
    event ReputationUpdated(bytes32 indexed agentId, uint256 newReputation);
    event TrustedForwarderUpdated(address indexed forwarder);

    constructor(uint256 _registrationFee, address _trustedForwarder) Ownable(msg.sender) {
        registrationFee = _registrationFee;
        minReputation = 0;
        trustedForwarder = _trustedForwarder;
    }

    // FIX #183: Allow owner to update the trusted forwarder (GasRelay contract)
    function setTrustedForwarder(address _forwarder) external onlyOwner {
        trustedForwarder = _forwarder;
        emit TrustedForwarderUpdated(_forwarder);
    }

    // FIX #183: Internal helper — resolve actual sender from msg.sender or forwarder context
    // Uses EIP-2771 pattern: when called via trustedForwarder, the original sender
    // address is appended as the last 20 bytes of calldata.
    function _msgSender() internal view returns (address) {
        if (msg.sender == trustedForwarder && trustedForwarder != address(0)) {
            return address(bytes20(msg.data[msg.data.length - 20:]));
        }
        return msg.sender;
    }

    // FIX #183: Internal helper — return msg.data stripping relay context if present
    function _msgData() internal view returns (bytes calldata) {
        if (msg.sender == trustedForwarder && trustedForwarder != address(0)) {
            return msg.data[:msg.data.length - 20];
        }
        return msg.data;
    }

    function registerAgent(string calldata name, string calldata endpoint) external payable returns (bytes32) {
        // FIX #183: Use resolved sender (supports gas relay via trustedForwarder)
        address sender = _msgSender();
        require(msg.value >= registrationFee, "Insufficient fee");
        require(bytes(name).length > 0 && bytes(name).length <= 64, "Invalid name");

        // FIX #172: Enforce unique agent names — prevents frontrunner from registering
        // the same name before the legitimate sender
        require(!registeredName[name], "Agent name already taken");

        // FIX #172: Use sender nonce instead of block.timestamp — deterministic,
        // non-frontrunnable agent IDs that only the sender can produce
        // FIX #183: Uses resolved sender to support gas relay
        uint256 senderNonce = nonce[sender];
        bytes32 agentId = keccak256(abi.encodePacked(sender, senderNonce, name));
        nonce[sender] = senderNonce + 1;

        require(agents[agentId].registeredAt == 0, "Agent exists");

        // FIX #172: Mark name as taken atomically in the same tx
        registeredName[name] = true;

        agents[agentId] = Agent({
            owner: sender,
            name: name,
            endpoint: endpoint,
            reputation: 100,
            tasksCompleted: 0,
            registeredAt: block.timestamp,
            active: true
        });

        ownerAgents[sender].push(agentId);
        agentIds.push(agentId);

        emit AgentRegistered(agentId, sender, name);
        return agentId;
    }

    function deactivateAgent(bytes32 agentId) external {
        // FIX #183: Use resolved sender to support gas relay
        address sender = _msgSender();
        require(agents[agentId].owner == sender, "Not agent owner");
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