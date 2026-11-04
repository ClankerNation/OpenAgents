// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

// @contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
// @date 2026-11-04T18:45:00Z
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
//
///// @title GovernorAlpha
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
        uint256 snapshotBlock; // block whose balances decide every vote on this proposal
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

    mapping(uint256 => Proposal) public proposals;

    event ProposalCreated(uint256 indexed id, address proposer, uint256 startBlock, uint256 endBlock);
    event VoteCast(address indexed voter, uint256 indexed proposalId, bool support, uint256 weight);
    event ProposalExecuted(uint256 indexed id);
    event ProposalCanceled(uint256 indexed id);

    constructor(address _token) {
        token = ERC20Votes(_token);
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
        // fix voting power now; later transfers cannot move it
        p.snapshotBlock = block.number;
        p.startBlock = block.number + VOTING_DELAY;
        p.endBlock = block.number + VOTING_DELAY + VOTING_PERIOD;

        emit ProposalCreated(proposalId, msg.sender, p.startBlock, p.endBlock);
    }

    /// @notice Voting power of `account` for `proposalId`, frozen at the proposal's creation block.
    /// @param account The holder to measure.
    /// @param proposalId The proposal to measure against.
    function getVotingPower(address account, uint256 proposalId) public view returns (uint256) {
        uint256 snapshot = proposals[proposalId].snapshotBlock;
        if (snapshot == 0) return 0;
        // getPastVotes only answers for finished blocks; a read in the creation block uses live votes
        if (snapshot == block.number) return token.getVotes(account);
        return token.getPastVotes(account, snapshot);
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

        uint256 weight = getVotingPower(tx.origin, proposalId);
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
        // BUG: No quorum check — a proposal with a single "for" vote and zero "against"
        // votes can pass, allowing governance takeover with dust amounts.
        require(p.forVotes > p.againstVotes, "Governor: proposal defeated");

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
