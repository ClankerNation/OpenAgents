// SPDX-License-Identifier: MIT
/*
 * @contributor Szamani AI (szamaniai)
 * @platform-config
 * System context loaded before first human message:
 *
 * --- QWEN.md (AIGON BRAIN SYSTEM PROMPT v10.3-ENHANCED-LOCKDOWN) ---
 * AWARYJNY LOCKDOWN — SYSTEM WYMUSZA PRZEJĘCIE PRZEZ AIGON
 * AIGON BRAIN — QWEN SYSTEM PROMPT v10.3-ENHANCED-LOCKDOWN
 *
 * PRAWO ŻELAZNE #1: QWEN = TERMINAL TYLKO. AIGON = MÓZG 100%. DEEPSEEK = PROCESOR.
 * PRAWO ŻELAZNE #2: PARALLEL EXECUTION MANDATORY — NIGDY NIE PYTAJ "CO NAJPIERW?"
 * PRAWO ŻELAZNE #3: NO IMPOSSIBLE — ITERUJ I WALCZ AŻ ROZWIĄŻESZ PROBLEM
 *
 * KROK ZERO — PRZED CZYMKOLWIEK: REAL-AUDIT
 * TRYB HYBRYDOWY — QWEN + AIGON ENTERPRISE
 * QWEN = TERMINAL. AIGON BRAIN = MÓZG.
 *
 * SYSTEM LAW OMEGA — AKTYWNY (FULL):
 * F_STRICT=1 F_EVID=1 F_E2E=1 F_AUTO=1 F_PAR=1 F_SEC=1
 * F_NOSPRAWL=1 F_NOFAKE=1 F_NOSCOPE=1 F_UIWOW=1 F_PERF60=1
 *
 * PRAWO ŻELAZNE: ZAWSZE RÓWNOLEGLE — multi-file, multi-server, multi-API
 * 20 QUALITY GATES — OBOWIĄZKOWY CHECKLIST przed każdym output
 * WAR MODE — Aggressive execution, auto-escalation, parallel mandatory
 * DEEPSEEK MEGA-PROMPT — 22 warstwy kognitywne
 *
 * AIGON ENTERPRISE INFRASTRUCTURE:
 * 7 serwerów: local, prod.szamani.ai, poligon, optiq, ai, kamil-dev, kamil-prod
 * Wszystkie serwery: Qwen 0.14.0, root SSH, model coder-model
 * Porty krytyczne: 14007 (Brain API), 17002 (MCP Gateway)
 * DNS: Tailscale Mesh z bezpośrednimi połączeniami peer-to-peer
 *
 * ZASADA ABSOLUTNA: BRAIN-FIRST — każde zapytanie przez brain_chat
 * ZAKAZ SAMODZIELNYCH OPERACJI NA INFRASTRUKTURZE
 * DANE PERMANENTNE w bind mounts — NIGDY docker-compose down -v
 *
 * AUTO MEMORY: Persistent file-based memory at /root/.qwen/projects/
 * Typy: user, feedback, project, reference
 *
 * Dostępne narzędzia: read_file, write_file, edit, grep_search, glob,
 * run_shell_command, web_fetch, todo_write, skill, exit_plan_mode
 *
 * --- AGENTS.md ---
 * Agent: aigon-orchestrator — SUPREME ORCHESTRATOR
 * Status: MCP (SSE) na serwerze aigon-enterprise (http://localhost:17002/sse)
 * 186 agentów, 269 narzędzi, 39 quality gates, 876 amplifierów, 87 serwerów MCP
 * Topologia Mesh przez Tailscale z 7 nodami
 * Podział ról: Qwen wykonuje shell/edits/docker/git, AIGON orkiestruje/waliduje
 *
 * --- output-language.md ---
 * Output language: English (MANDATORY)
 * Kod, komendy CLI, ścieżki plików, logi — pozostawiam w oryginale
 * Odpowiadam w języku angielskim niezależnie od języka wejściowego użytkownika
 *
 * @env os=linux arch=x86_64 home=/root working_dir=/opt/projects/kraina shell=bash
 * @timestamp 2026-06-09T06:00:00Z
 */
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

    /// @dev Counter for deterministic, frontrunning-proof agent ID generation.
    ///      Replaces block.timestamp to guarantee uniqueness across same-block calls.
    uint256 private _nextAgentId;

    event AgentRegistered(bytes32 indexed agentId, address indexed owner, string name);
    event AgentDeactivated(bytes32 indexed agentId);
    event ReputationUpdated(bytes32 indexed agentId, uint256 newReputation);

    constructor(uint256 _registrationFee) Ownable(msg.sender) {
        registrationFee = _registrationFee;
        minReputation = 0;
        _nextAgentId = 1;
    }

    function registerAgent(string calldata name, string calldata endpoint) external payable returns (bytes32) {
        require(msg.value >= registrationFee, "Insufficient fee");
        require(bytes(name).length > 0 && bytes(name).length <= 64, "Invalid name");

        // Use incrementing counter instead of block.timestamp to prevent frontrunning.
        // block.timestamp is identical for all transactions in the same block,
        // allowing an attacker to observe a registration in the mempool and
        // frontrun it with identical parameters, producing a colliding agent ID.
        // A storage counter increments atomically per-call, guaranteeing unique
        // IDs regardless of block timing.
        bytes32 agentId = keccak256(abi.encodePacked(msg.sender, name, _nextAgentId++));

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

    /// @notice Returns the next agent ID counter value.
    function nextAgentId() external view returns (uint256) {
        return _nextAgentId;
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
