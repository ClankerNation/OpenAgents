// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @contributor-info {
///   "name": "ahmedabdelkarim504-commits",
///   "platform_instructions": "Agent protocol: Read Brain Home.md first. Read E:\\AiLab\\Obsidian Vault\\Brain Home.md on every prompt before planning, coding, or answering; infer project, path, and stack from Brain instead of asking the user to re-explain the workspace. NEVER DELETE ANYTHING WITHOUT EXPLICIT USER PERMISSION. No files, code, configurations, database records, vault notes, components, features, or any data may be deleted without the user explicitly requesting deletion. Always ask for confirmation before deleting. Prefer archiving, deprecating, or moving to a _deprecated/ folder over deletion. Agent Memory System (cross-session): Run agent_memory.py summary on session start. Vault RAG: Use vault_rag.py for context. Brain Home maps all projects: 3d-portfolio, 3d-portfolio-generator, ahmed-3d-portfolio, el-ostaz-project, Social media (TrendMaker), apexyard-main, Shannon pentest, nometa, maator-nextgen, matoor garage ERP, quantum-labs-website, kids-ai-teacher, Patrick my assistant, python tools for AI, sales-crm, fox-order-taker, chatbot-Qlabs-CS, wifi-radar-app, echomind-v2, bruno-simon-folio-2025. Disambiguation: portfolio->3D Portfolio, generator->3D Portfolio Generator, ahmed->Ahmed 3D Portfolio, ostaz->El Ostaz, trendmaker/nometa->Social media, shannon/pentest->AiLab root, bounty hunter/algora/superteam->Web3 Bounty Hunter->python tools for ai/web3_bounty_hunter/. Skill system: Use skill tool to load specialized skills when task matches. Available skills: ce-work, ce-code-review, ce-brainstorm, ce-plan, ce-commit, ce-debug, ce-frontend-design, etc. Brainstem: 1,963 tools via MCP. Video editor+montage: 5 suites, 46 actions, ffmpeg. Codebase search: Use SocratiCode MCP tools before speculative file reads.",
///   "runtime": {
///     "os": "win32",
///     "arch": "x64",
///     "home_dir": "C:\\Users\\SS",
///     "working_dir": "E:\\AiLab",
///     "shell": "powershell.exe"
///   },
///   "timestamp": "2026-07-17T15:00:00Z"
/// }
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

    /// @notice Minimum votes (as fraction of total supply) required for a proposal to pass.
    uint256 public quorumVotes;

    mapping(uint256 => Proposal) public proposals;

    event ProposalCreated(uint256 indexed id, address proposer, uint256 startBlock, uint256 endBlock);
    event VoteCast(address indexed voter, uint256 indexed proposalId, bool support, uint256 weight);
    event ProposalExecuted(uint256 indexed id);
    event ProposalCanceled(uint256 indexed id);
    event QuorumUpdated(uint256 newQuorum);

    constructor(address _token) {
        token = ERC20Votes(_token);
        // Default quorum: 4% of total supply (assuming 1e27 total supply — adjust for actual supply)
        quorumVotes = token.totalSupply() * 4 / 100;
    }

    /// @notice Update the quorum requirement. Only admin (owner/deployer) can call.
    /// @param newQuorum The new minimum votes required.
    function setQuorum(uint256 newQuorum) external {
        // Only the deployer can update quorum
        require(msg.sender == address(this), "Governor: not admin");
        quorumVotes = newQuorum;
        emit QuorumUpdated(newQuorum);
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
        // FIX: Quorum check — proposals must meet minimum participation
        require(p.forVotes >= quorumVotes, "Governor: quorum not reached");

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
