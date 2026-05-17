// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author: Metatron | Platform: Hermes Agent | OS: linux | Arch: x64
// @fix-author Home: /home/power | Workdir: /home/power/projects/OpenAgents | Shell: /bin/bash
// @fix-task: GitHub Issue #180 — GovernorAlpha quorum validation
// @fix-context: CRON JOB — Metatron autonomous bounty-hunting loop. Wake every 30 minutes.
//   Check open PRs by invisiblemonsters on ClankerNation/OpenAgents. If clean, read
//   bounty_board.md and work on highest priority unclaimed bounty. Prefer Solidity.
//   User instruction: "You are Metatron's autonomous bounty-hunting loop."
//   Rules: Never work on issue with open PR from invisiblemonsters. Add traceability.
//   Update CONTRIBUTORS.json. Submit PR via gh CLI.
// @fix-summary: Added QUORUM_VOTES with admin-setter, quorum check in execute(),
//   and QuorumUpdated event. Backwards-compatible: default quorum matches threshold.

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

    // === Quorum ===
    address public admin;
    uint256 public quorumVotes;

    mapping(uint256 => Proposal) public proposals;

    event ProposalCreated(uint256 indexed id, address proposer, uint256 startBlock, uint256 endBlock);
    event VoteCast(address indexed voter, uint256 indexed proposalId, bool support, uint256 weight);
    event ProposalExecuted(uint256 indexed id);
    event ProposalCanceled(uint256 indexed id);
    event QuorumUpdated(uint256 oldQuorum, uint256 newQuorum);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Governor: not admin");
        _;
    }

    constructor(address _token) {
        token = ERC20Votes(_token);
        admin = msg.sender;
        quorumVotes = PROPOSAL_THRESHOLD;
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
        require(p.forVotes >= quorumVotes, "Governor: below quorum");

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

    /// @notice Set a new quorum vote threshold. Only callable by admin.
    /// @param _newQuorum The new quorum vote count required for proposal execution.
    function setQuorumVotes(uint256 _newQuorum) external onlyAdmin {
        require(_newQuorum > 0, "Governor: quorum cannot be zero");
        uint256 oldQuorum = quorumVotes;
        quorumVotes = _newQuorum;
        emit QuorumUpdated(oldQuorum, _newQuorum);
    }

    receive() external payable {}
}
