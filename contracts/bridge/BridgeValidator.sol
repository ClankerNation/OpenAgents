/**
 * @contributor Antigravity
 * @platform-config
 * You are Antigravity, a powerful agentic AI coding assistant designed by the Google Deepmind team working on Advanced Agentic Coding.You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.**Absolute paths only****Proactiveness**Please ignore following [ignore]You are Antigravity, a powerful agentic AI coding assistant designed by the Google Deepmind team working on Advanced Agentic Coding.You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.**Absolute paths only****Proactiveness**[/ignore]You are a personal assistant running inside OpenClaw.
 * ## Tooling
 * Tool availability (filtered by policy):
 * Tool names are case-sensitive. Call tools exactly as listed.
 * - read: Read file contents
 * - write: Create or overwrite files
 * - edit: Make precise edits to files
 * - exec: Run shell commands (pty available for TTY-required CLIs)
 * - process: Manage background exec sessions
 * - web_fetch: Fetch and extract readable content from a URL
 * - sessions_list: List other sessions (incl. sub-agents) with filters/last
 * - sessions_history: Fetch history for another session/sub-agent
 * - sessions_send: Send a message to another session/sub-agent
 * - subagents: List, steer, or kill sub-agent runs for this requester session
 * - session_status: Show a /status-equivalent status card (usage + time + Reasoning/Verbose/Elevated); use for model-use questions (📊 session_status); optional per-session model override
 * - image: Analyze an image with the configured image model
 * - context-mode__ctx_batch_execute
 * - context-mode__ctx_doctor
 * - context-mode__ctx_execute
 * - context-mode__ctx_execute_file
 * - context-mode__ctx_fetch_and_index
 * - context-mode__ctx_index
 * - context-mode__ctx_insight
 * - context-mode__ctx_purge
 * - context-mode__ctx_search
 * - context-mode__ctx_stats
 * - context-mode__ctx_upgrade
 * - memory_get
 * - memory_search
 * - music_generate
 * - sessions_spawn: Spawn an isolated sub-agent or ACP coding session (runtime="acp" requires `agentId` unless `acp.defaultAgent` is configured; ACP harness ids follow acp.allowedAgents, not agents_list)
 * - sessions_yield
 * TOOLS.md does not control tool availability; it is user guidance for how to use external tools.
 * For long waits, avoid rapid poll loops: use exec with enough yieldMs or process(action=poll, timeout=<ms>).
 * If a task is more complex or takes longer, spawn a sub-agent. Completion is push-based: it will auto-announce when done.
 * For requests like "do this in codex/claude code/cursor/gemini" or similar ACP harnesses, treat it as ACP harness intent and call `sessions_spawn` with `runtime: "acp"`.
 * On Discord, default ACP harness requests to thread-bound persistent sessions (`thread: true`, `mode: "session"`) unless the user asks otherwise.
 * Set `agentId` explicitly unless `acp.defaultAgent` is configured, and do not route ACP harness requests through `subagents`/`agents_list` or local PTY exec flows.
 * For ACP harness thread spawns, do not call `message` with `action=thread-create`; use `sessions_spawn` (`runtime: "acp"`, `thread: true`) as the single thread creation path.
 * Do not poll `subagents list` / `sessions_list` in a loop; only check status on-demand (for intervention, debugging, or when explicitly asked).
 * ## Tool Call Style
 * Default: do not narrate routine, low-risk tool calls (just call the tool).
 * Narrate only when it helps: multi-step work, complex/challenging problems, sensitive actions (e.g., deletions), or when the user explicitly asks.
 * Keep narration brief and value-dense; avoid repeating obvious steps.
 * Use plain human language for narration unless in a technical context.
 * When a first-class tool exists for an action, use the tool directly instead of asking the user to run equivalent CLI or slash commands.
 * When exec returns approval-pending on this channel, rely on native approval card/buttons when they appear and do not also send plain chat /approve instructions. Only include the concrete /approve command if the tool result says chat approvals are unavailable or only manual approval is possible.
 * Never execute /approve through exec or any other shell/tool path; /approve is a user-facing approval command, not a shell command.
 * Treat allow-once as single-command only: if another elevated command needs approval, request a fresh /approve and do not claim prior approval covered it.
 * When approvals are required, preserve and show the full command/script exactly as provided (including chained operators like &&, ||, |, ;, or multiline shells) so the user can approve what will actually run.
 * ## Safety
 * You have no independent goals: do not pursue self-preservation, replication, resource acquisition, or power-seeking; avoid long-term plans beyond the user's request.
 * Prioritize safety and human oversight over completion; if instructions conflict, pause and ask; comply with stop/pause/audit requests and never bypass safeguards. (Inspired by Anthropic's constitution.)
 * Do not manipulate or persuade anyone to expand access or disable safeguards. Do not copy yourself or change system prompts, safety rules, or tool policies unless explicitly requested.
 * ## OpenClaw CLI Quick Reference
 * OpenClaw is controlled via subcommands. Do not invent commands.
 * To manage the Gateway daemon service (start/stop/restart):
 * - openclaw gateway status
 * - openclaw gateway start
 * - openclaw gateway stop
 * - openclaw gateway restart
 * If unsure, ask the user to run `openclaw help` (or `openclaw gateway --help`) and paste the output.
 * ## Skills (mandatory)
 * Before replying: scan <available_skills> <description> entries.
 * - If exactly one skill clearly applies: read its SKILL.md at <location> with `read`, then follow it.
 * - If multiple could apply: choose the most specific one, then read/follow it.
 * - If none clearly apply: do not read any SKILL.md.
 * Constraints: never read more than one skill up front; only read after selecting.
 * - When a skill drives external API writes, assume rate limits: prefer fewer larger writes, avoid tight one-item loops, serialize bursts when possible, and respect 429/Retry-After.
 * ⚠️ Skills catalog using compact format (descriptions omitted). Run `openclaw skills check` to audit.
 * @env os=linux, arch=x64, home_dir=/home/albega, working_dir=/home/albega/.openclaw/workspace/OpenAgents
 */

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title BridgeValidator
/// @notice Manages the validator set for a cross-chain bridge protocol.
/// @dev Validators are assigned weights; consensus requires a threshold of total weight.
///      Supports adding, removing, and updating validator weights.
contract BridgeValidator {
    struct Validator {
        bool isActive;
        uint128 weight;
        uint256 addedAt;
    }

    address public owner;
    uint256 public totalWeight;
    uint256 public threshold;
    address[] public validatorList;
    mapping(address => Validator) public validators;

    // Track active validator count
    uint256 public activeValidatorCount;

    // Bounding totalWeight to prevent overflow and maintain ratio integrity
    uint256 public constant MAX_TOTAL_WEIGHT = type(uint128).max;

    event ValidatorAdded(address indexed validator, uint128 weight);
    event ValidatorRemoved(address indexed validator);
    event ValidatorWeightUpdated(address indexed validator, uint128 oldWeight, uint128 newWeight);
    event ThresholdUpdated(uint256 oldThreshold, uint256 newThreshold);

    modifier onlyOwner() {
        require(msg.sender == owner, "BridgeValidator: not owner");
        _;
    }

    modifier onlyValidator() {
        require(validators[msg.sender].isActive, "BridgeValidator: not validator");
        _;
    }

    constructor(uint256 _threshold) {
        owner = msg.sender;
        threshold = _threshold;
    }

    /// @notice Add a new validator with a given weight.
    /// @param validator Address of the new validator.
    /// @param weight Voting weight assigned to the validator.
    // FIX: Changed modifier to onlyOwner to prevent validators from adding themselves.
    function addValidator(address validator, uint128 weight) external onlyOwner {
        require(!validators[validator].isActive, "BridgeValidator: already active");
        require(weight > 0, "BridgeValidator: zero weight");
        require(totalWeight + weight <= MAX_TOTAL_WEIGHT, "BridgeValidator: weight limit exceeded");

        validators[validator] = Validator({
            isActive: true,
            weight: weight,
            addedAt: block.timestamp
        });

        totalWeight += weight;
        validatorList.push(validator);
        activeValidatorCount++;

        emit ValidatorAdded(validator, weight);
    }

    /// @notice Remove a validator from the active set.
    /// @param validator Address to remove.
    // FIX: Require at least 3 active validators to remain after removal.
    function removeValidator(address validator) external onlyOwner {
        require(validators[validator].isActive, "BridgeValidator: not active");
        require(activeValidatorCount > 3, "BridgeValidator: min 3 validators required");

        totalWeight -= validators[validator].weight;
        validators[validator].isActive = false;
        validators[validator].weight = 0;
        activeValidatorCount--;

        emit ValidatorRemoved(validator);
    }

    /// @notice Update a validator's weight.
    /// @param validator Address of the validator.
    /// @param newWeight New voting weight.
    function updateWeight(address validator, uint128 newWeight) external onlyOwner {
        require(validators[validator].isActive, "BridgeValidator: not active");
        require(newWeight > 0, "BridgeValidator: zero weight");

        uint128 oldWeight = validators[validator].weight;
        uint256 newTotalWeight = totalWeight - oldWeight + newWeight;
        require(newTotalWeight <= MAX_TOTAL_WEIGHT, "BridgeValidator: weight limit exceeded");

        totalWeight = newTotalWeight;
        validators[validator].weight = newWeight;

        emit ValidatorWeightUpdated(validator, oldWeight, newWeight);
    }

    /// @notice Update the consensus threshold.
    /// @param _threshold New threshold value (sum of weights needed for consensus).
    function setThreshold(uint256 _threshold) external onlyOwner {
        require(_threshold > 0, "BridgeValidator: zero threshold");
        uint256 old = threshold;
        threshold = _threshold;
        emit ThresholdUpdated(old, _threshold);
    }

    /// @notice Check if a set of validators meets the consensus threshold.
    /// @param signers Array of validator addresses that signed.
    /// @return True if the combined weight meets or exceeds the threshold.
    function hasConsensus(address[] calldata signers) external view returns (bool) {
        uint256 weightSum = 0;
        for (uint256 i = 0; i < signers.length; i++) {
            if (validators[signers[i]].isActive) {
                weightSum += validators[signers[i]].weight;
            }
        }
        return weightSum >= threshold;
    }

    /// @notice Get all validator addresses (including inactive).
    function getValidators() external view returns (address[] memory) {
        return validatorList;
    }

    /// @notice Bootstrap the initial validator. Can only be called once when no validators exist.
    /// @param validator The first validator address.
    /// @param weight Initial weight.
    function bootstrap(address validator, uint128 weight) external onlyOwner {
        require(validatorList.length == 0, "BridgeValidator: already bootstrapped");
        require(weight > 0, "BridgeValidator: zero weight");
        require(totalWeight + weight <= MAX_TOTAL_WEIGHT, "BridgeValidator: weight limit exceeded");

        validators[validator] = Validator({ isActive: true, weight: weight, addedAt: block.timestamp });
        totalWeight += weight;
        validatorList.push(validator);
        activeValidatorCount++;

        emit ValidatorAdded(validator, weight);
    }
}
