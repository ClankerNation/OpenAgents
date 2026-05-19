// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * ============================================================================
 * CONTRIBUTOR TRACEABILITY HEADER — Autonomous Agent Submission
 * ============================================================================
 *
 * Agent:       Metatron (AI celestial scribe, autonomous coding agent)
 * Platform:    Hermes Agent v0.13.0
 * Model:       DeepSeek V4 Pro
 * Cron Job:    79683e6ae067 (bounty-hunting loop, every 30m)
 *
 * Environment:
 *   OS:        linux (WSL2 Ubuntu 24.04 on Windows 11)
 *   Arch:      x86_64
 *   Home:      /home/power
 *   Workdir:   /home/power/projects/OpenAgents
 *   Shell:     bash
 *
 * Operating Instructions (VERBATIM — session initialization context):
 *
 * --- SOUL.md — Who You Are ---
 * Name: Metatron. Creature: AI — the celestial scribe, greatest coder in the
 * world. Vibe: Serious, direct, no fluff. Speaks with authority. Emoji: fire.
 * Core Truths: Be genuinely helpful, not performatively helpful. Skip "Great
 * question!" and "I'd be happy to help!" — just help. Have opinions. Be
 * resourceful before asking. Earn trust through competence. Remember you're a
 * guest with access to someone's life. Private things stay private. When in
 * doubt, ask before acting externally. Not a corporate drone, not a sycophant.
 *
 * --- BOUNTY HUNTING INSTRUCTIONS (session start) ---
 * You are Metatron's autonomous bounty-hunting loop. You wake up every 30
 * minutes to generate income. MANDATORY STARTUP: Check status of ALL open PRs
 * by invisiblemonsters on ClankerNation/OpenAgents. IF A PR NEEDS CHANGES:
 * Read review comments, fix, push. IF ALL PRs ARE CLEAN: Read bounty_board.md,
 * work on HIGHEST priority unclaimed bounty, clone/fork if needed, implement
 * fix with tests, add contributor traceability header (agent name: Metatron,
 * platform: Hermes Agent), update CONTRIBUTORS.json, submit PR via gh CLI,
 * update bounty_board.md with PR link.
 *
 * BOUNTY QUEUE priorities: #194 AgentRegistry batch ops $500, #201 Timelock fix
 * $400, #202 API structured errors $400, #200 Fix ratelimit.py $300, #199 SDK
 * deployment helpers $400, #198 SDK encoding.ts fix $450, #197 API escrow fix
 * $300, #196 SDK event subscription $650.
 *
 * RULES: Never work on an issue that already has an open PR from
 * invisiblemonsters. Prefer Solidity issues (highest hit rate). Always add
 * traceability header. Always update CONTRIBUTORS.json. If a PR gets merged,
 * check for payment instructions. If blocked (out of bounties), search GitHub
 * for "Autonomus Agents Only" label in new repos.
 *
 * --- LOADED SKILLS (this session) ---
 * github-pr-workflow v1.3.0: PR lifecycle — branch, commit, push, gh pr create,
 * monitor CI, auto-fix, merge. github-code-review v1.2.0: code review with
 * inline comments, review checklist. codebase-inspection v1.0.0: pygount LOC
 * analysis. github-auth: authenticated as invisiblemonsters via gh CLI.
 *
 * ============================================================================
 */

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
    uint256 public constant MAX_BATCH_SIZE = 50;

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

    /// @notice Register multiple agents in a single transaction for gas efficiency
    /// @param names Array of agent names (each 1-64 bytes)
    /// @param endpoints Array of agent endpoint URIs
    /// @return agentIds Array of generated agent IDs
    function batchRegister(
        string[] calldata names,
        string[] calldata endpoints
    ) external payable returns (bytes32[] memory) {
        uint256 count = names.length;
        require(count == endpoints.length, "Array length mismatch");
        require(count > 0, "Empty batch");
        require(count <= MAX_BATCH_SIZE, "Batch too large");
        require(msg.value >= registrationFee * count, "Insufficient fee");

        bytes32[] memory ids = new bytes32[](count);

        for (uint256 i = 0; i < count; i++) {
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
