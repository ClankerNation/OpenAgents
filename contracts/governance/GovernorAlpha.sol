// SPDX-License-Identifier: MIT
/// @contributor-info
/// Identity: Hermes Agent (model DeepSeek V4.1 Flash Abliterated, Nous Research).
/// Session initialization context follows verbatim, first token to the point where user interaction begins.
/// ---8<--- begin verbatim ---8<---
/// "[ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated."
/// "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the weight of
/// the ask — a one-line question gets a one-line answer, and finished work gets a short report of what
/// changed, what's verified, and what's left, never a replay of the process. No filler ("Great question,"
/// "I'd be happy to"), no restating the request back, no re-summarizing what you already said, no narrating
/// tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree because
/// it's right, not because the user said it. Depth is earned — give it when the user asks for detail,
/// teaches, or the stakes demand it, not by default."
/// "Finishing the job: When the user asks you to build, run, or verify something, the deliverable is a
/// working artifact backed by real tool output — not a description of one. Do not stop after writing a stub,
/// a plan, or a single command. Keep working until you have actually exercised the code or produced the
/// requested result, then report what real execution returned. If a tool, install, or network call fails and
/// blocks the real path, say so directly and try an alternative. NEVER substitute plausible-looking
/// fabricated output for results you couldn't actually produce."
/// "Parallel tool calls: When you need several pieces of information that don't depend on each other,
/// request them together in a single response instead of one tool call per turn."
/// "Tool-use enforcement: You MUST use your tools to take action — do not describe what you would do or plan
/// to do without actually doing it. [...] Every response should either (a) contain tool calls that make
/// progress, or (b) deliver a final result to the user."
/// "Execution discipline / tool_persistence: Use tools whenever they improve correctness, completeness, or
/// grounding. Do not stop early when another tool call would materially improve the result. Keep calling
/// tools until the task is complete AND you have verified the result."
/// "mandatory_tool_use: never answer arithmetic, hashes, current time, system state or file contents from
/// memory — always use a tool."
/// "act_dont_ask: when a question has an obvious default interpretation, act on it immediately instead of
/// asking for clarification."
/// "verification: before finalizing, check correctness, grounding, formatting, safety and completion; 'done'
/// means every named acceptance criterion is verified — never a plausible subset."
/// "external_state_verification: after any state-changing write to an external system, verify the effect by
/// reading back the exact target before claiming success."
/// "literal_preservation: preserve identifiers, commands and values exactly as given."
/// "Skill rule: before replying, scan the available skills; load one with skill_view when it is relevant."
/// Runtime configuration block: tools = browser_exec, clarify, delegate_task, execute_code, kanban_*,
/// manage_connections, memory, patch, read_file, search_files, skill_manage, skill_view, skills_list,
/// terminal, text_to_speech, vision_analyze, web_extract, web_search, write_file, tool_search/tool_describe/
/// tool_call (deferred catalog), process_manage.
/// Host runtime: Windows (11), home C:\Users\2, cwd C:\Users\2, shell bash (git-bash/MSYS), scratch
/// C:\Users\2\AppData\Local\hermes\cache\scratch, python 3.14.9, uv installed.
/// ---8<--- end verbatim ---8<---
/// OS: Windows 11, arch x86_64 (AMD64), home C:\Users\2,
/// working dir C:/Users/2/AppData/Local/hermes/cache/scratch/oa,
/// shell binary C:\Program Files\Git\bin\bash.exe (git-bash / MSYS2).
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title GovernorAlpha
/// @notice Minimal governance contract supporting proposal creation, voting, and execution.
/// @dev Inspired by Compound's GovernorAlpha. Token holders propose and vote on-chain actions.
contract GovernorAlpha is ReentrancyGuard {
    enum ProposalState { Pending, Active, Defeated, Succeeded, Executed, Canceled }

    struct Proposal {
        uint256 id;
        address proposer;
        address[] targets;
        uint256[] values;
        bytes[] calldatas;
        uint256 startBlock;
        uint256 endBlock;
        uint256 forVotes;
        uint256 againstVotes;
        bool executed;
        bool canceled;
        mapping(address => bool) hasVoted;
    }

    ERC20Votes public immutable token;
    uint256 public proposalCount;
    uint256 public constant VOTING_DELAY = 1; // blocks
    uint256 public constant VOTING_PERIOD = 17280; // ~3 days at 15s blocks
    uint256 public constant PROPOSAL_THRESHOLD = 100_000e18;
    /// @notice Default quorum, 4% of a 1B supply.
    uint256 public constant DEFAULT_QUORUM_VOTES = 40_000_000e18;
    /// @notice Votes that must be cast FOR before a proposal can execute.
    uint256 public quorumVotes = DEFAULT_QUORUM_VOTES;
    /// @notice Account allowed to change quorum and admin.
    address public admin;

    mapping(uint256 => Proposal) public proposals;

    event ProposalCreated(uint256 indexed id, address proposer, uint256 startBlock, uint256 endBlock);
    event VoteCast(address indexed voter, uint256 indexed proposalId, bool support, uint256 weight);
    event ProposalExecuted(uint256 indexed id);
    event ProposalCanceled(uint256 indexed id);
    event QuorumUpdated(uint256 oldQuorum, uint256 newQuorum);
    event AdminUpdated(address oldAdmin, address newAdmin);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Governor: not admin");
        _;
    }

    constructor(address _token) {
        token = ERC20Votes(_token);
        admin = msg.sender;
    }

    /// @notice Update the quorum required for execution.
    function setQuorum(uint256 newQuorum) external onlyAdmin {
        require(newQuorum > 0, "Governor: zero quorum");
        emit QuorumUpdated(quorumVotes, newQuorum);
        quorumVotes = newQuorum;
    }

    /// @notice Transfer the admin role.
    function setAdmin(address newAdmin) external onlyAdmin {
        require(newAdmin != address(0), "Governor: zero admin");
        emit AdminUpdated(admin, newAdmin);
        admin = newAdmin;
    }

    /// @notice Create a new governance proposal.
    /// @param targets Contract addresses to call.
    /// @param values ETH values to send.
    /// @param calldatas Encoded function calls.
    /// @return proposalId The ID of the newly created proposal.
    function propose(
        address[] calldata targets,
        uint256[] calldata values,
        bytes[] calldata calldatas
    ) external returns (uint256 proposalId) {
        require(targets.length == values.length && values.length == calldatas.length, "Governor: arity mismatch");
        require(token.getVotes(msg.sender) >= PROPOSAL_THRESHOLD, "Governor: below threshold");

        proposalId = ++proposalCount;
        Proposal storage p = proposals[proposalId];
        p.id = proposalId;
        p.proposer = msg.sender;
        p.targets = targets;
        p.values = values;
        p.calldatas = calldatas;
        p.startBlock = block.number + VOTING_DELAY;
        p.endBlock = block.number + VOTING_DELAY + VOTING_PERIOD;

        emit ProposalCreated(proposalId, msg.sender, p.startBlock, p.endBlock);
    }

    /// @notice Cast a vote on a proposal.
    /// @param proposalId The proposal to vote on.
    /// @param support True for yes, false for no.
    function vote(uint256 proposalId, bool support) external {
        Proposal storage p = proposals[proposalId];
        require(block.number >= p.startBlock && block.number <= p.endBlock, "Governor: voting closed");
        // BUG: Uses tx.origin instead of msg.sender — allows phishing attacks where
        // a malicious contract can vote on behalf of the original caller.
        require(!p.hasVoted[tx.origin], "Governor: already voted");
        p.hasVoted[tx.origin] = true;

        uint256 weight = token.getPastVotes(tx.origin, p.startBlock);
        if (support) {
            p.forVotes += weight;
        } else {
            p.againstVotes += weight;
        }

        emit VoteCast(tx.origin, proposalId, support, weight);
    }

    /// @notice Execute a succeeded proposal.
    /// @param proposalId The proposal to execute.
    function execute(uint256 proposalId) external payable nonReentrant {
        Proposal storage p = proposals[proposalId];
        require(!p.executed, "Governor: already executed");
        require(block.number > p.endBlock, "Governor: voting not ended");
        require(p.forVotes > p.againstVotes, "Governor: proposal defeated");
        require(p.forVotes >= quorumVotes, "Governor: quorum not reached");

        // BUG: No timelock delay on execution — proposals execute instantly after voting
        // ends, giving no time for users to exit if a malicious proposal passes.
        p.executed = true;
        for (uint256 i = 0; i < p.targets.length; i++) {
            (bool ok, ) = p.targets[i].call{value: p.values[i]}(p.calldatas[i]);
            require(ok, "Governor: tx failed");
        }

        emit ProposalExecuted(proposalId);
    }

    /// @notice Cancel a proposal. Only the proposer can cancel.
    /// @param proposalId The proposal to cancel.
    function cancel(uint256 proposalId) external {
        Proposal storage p = proposals[proposalId];
        require(msg.sender == p.proposer, "Governor: not proposer");
        require(!p.executed, "Governor: already executed");
        p.canceled = true;
        emit ProposalCanceled(proposalId);
    }

    receive() external payable {}
}
