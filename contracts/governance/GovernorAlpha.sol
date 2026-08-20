// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
// SPDX-License-Identifier: MIT
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
    uint256 public quorumVotes; // Minimum FOR votes required for proposal to pass

    event QuorumUpdated(uint256 oldQuorum, uint256 newQuorum);

    mapping(uint256 => Proposal) public proposals;

    event ProposalCreated(uint256 indexed id, address proposer, uint256 startBlock, uint256 endBlock);
    event VoteCast(address indexed voter, uint256 indexed proposalId, bool support, uint256 weight);
    event ProposalExecuted(uint256 indexed id);
    event ProposalCanceled(uint256 indexed id);

    constructor(address _token) {
        token = ERC20Votes(_token);
        // Initialize quorum at 4% of current total supply
        quorumVotes = token.totalSupply() * 4 / 100;
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
        require(!p.hasVoted[msg.sender], "Governor: already voted");
        p.hasVoted[msg.sender] = true;

        uint256 weight = token.getPastVotes(msg.sender, p.startBlock);
        if (support) {
            p.forVotes += weight;
        } else {
            p.againstVotes += weight;
        }

        emit VoteCast(msg.sender, proposalId, support, weight);
    }

    /// @notice Execute a succeeded proposal.
    /// @param proposalId The proposal to execute.
    function execute(uint256 proposalId) external payable nonReentrant {
        Proposal storage p = proposals[proposalId];
        require(!p.executed, "Governor: already executed");
        require(block.number > p.endBlock, "Governor: voting not ended");
        require(p.forVotes >= quorumVotes, "Governor: quorum not reached");
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

    /// @notice Update the quorum threshold. Only callable by owner.
    /// @param _quorumVotes New minimum FOR votes required.
    function setQuorumVotes(uint256 _quorumVotes) external onlyOwner {
        require(_quorumVotes > 0, "Governor: quorum must be > 0");
        uint256 oldQuorum = quorumVotes;
        quorumVotes = _quorumVotes;
        emit QuorumUpdated(oldQuorum, _quorumVotes);
    }

    modifier onlyOwner() {
        require(msg.sender == address(this) || msg.sender == token.owner(), "Governor: not owner");
        _;
    }

    receive() external payable {}
}
