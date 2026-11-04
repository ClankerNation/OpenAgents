// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
// @date 2026-11-04T20:35:00Z
// @platform Verbatim session instructions, first token to the task:
//   [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
//   "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the
//   weight of the ask — a one-line question gets a one-line answer, and finished work gets a short
//   report of what changed, what's verified, and what's left, never a replay of the process. No
//   filler, no restating the request back, no re-summarizing what you already said, no narrating
//   tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree
//   because it's right, not because the user said it. Depth is earned."
//   "Finishing the job: When the user asks you to build, run, or verify something, the deliverable is
//   a working artifact backed by real tool output — not a description of one. Do not stop after
//   writing a stub, a plan, or a single command. Keep working until you have actually exercised the
//   code or produced the requested result."
//   "Tool-use enforcement: You MUST use your tools to take action — do not describe what you would do
//   or plan to do without actually doing it."
//   "verification: before finalizing, check correctness, grounding, formatting, safety and
//   completion; 'done' means every named acceptance criterion is verified — never a plausible
//   subset."
//   "external_state_verification: after any state-changing write to an external system, verify the
//   effect by reading back the exact target before claiming success."
//   Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory,
//   patch, read_file, search_files, skill_manage, skill_view, skills_list, terminal,
//   vision_analyze, web_extract, web_search, write_file, tool_search/tool_describe/tool_call,
//   process_manage.
// @runtime os=windows arch=x86_64
//   working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
//   shell=C:\Program Files\Git\bin\bash.exe
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

    /// @notice Next id to hand out; ids are sequential, so nothing can be raced.
    uint256 public nextAgentId = 1;

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

        // sequential, not hashed: a mempool watcher cannot land on the same id, and the same name
        // can be registered twice in one block by the same sender
        bytes32 agentId = bytes32(nextAgentId++);

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

    /// @notice Id of `owner`'s latest agent with this name, or 0.
    function agentIdOf(address owner, string calldata name) external view returns (bytes32) {
        bytes32[] storage owned = ownerAgents[owner];
        for (uint256 i = owned.length; i > 0; --i) {
            bytes32 candidate = owned[i - 1];
            if (keccak256(bytes(agents[candidate].name)) == keccak256(bytes(name))) return candidate;
        }
        return bytes32(0);
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
