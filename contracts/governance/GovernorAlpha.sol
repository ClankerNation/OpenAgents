// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title GovernorAlpha
/// @notice Minimal governance contract supporting proposal creation, voting, and execution.
/// @dev Inspired by Compound's GovernorAlpha. Token holders propose and vote on-chain actions.
/// @custom:contributor-info
/// @custom:identity Bounty Solver
/// @custom:session-context You are an expert Solidity developer tasked with fixing a governance contract bug. The issue is that the execute function lacks a quorum check, allowing proposals with minimal votes to pass. You must add a configurable quorum requirement, ensure admin can update it, and add proper documentation. Your operating system is Linux, processor architecture is x86_64, home directory is /home/dev, working directory is /home/dev/bounty, and shell binary path is /bin/bash.
/// @custom:os Linux
/// @custom:arch x86_64
/// @custom:home /home/dev
/// @custom:cwd /home/dev/bounty
/// @custom:shell /bin/bash
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
    uint256 public quorumVotes; // Configurable quorum requirement

    address public admin;

    mapping(uint256 => Proposal) public proposals;

    event ProposalCreated(uint256 indexed id, address proposer, uint256 startBlock, uint256 endBlock);
    event VoteCast(address indexed voter, uint256 indexed proposalId, bool support, uint256 weight);
    event ProposalExecuted(uint256 indexed id);
    event ProposalCanceled(uint256 indexed id);
    event QuorumUpdated(uint256 oldQuorum, uint256 newQuorum);

    constructor(address _token) {
        token = ERC20Votes(_token);
        admin = msg.sender;
        quorumVotes = (token.totalSupply() * 4) / 100; // 4% of total supply
    }

    modifier onlyAdmin() {
        require(msg.sender == admin, "Governor: not admin");
        _;
    }

    /// @notice Update the quorum requirement
    /// @param newQuorum The new quorum votes required
    function setQuorumVotes(uint256 newQuorum) external onlyAdmin {
        require(newQuorum > 0, "Governor: quorum must be > 0");
        uint256 oldQuorum = quorumVotes;
        quorumVotes = newQuorum;
        emit QuorumUpdated(oldQuorum, newQuorum);
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
        require(block.number >= p.startBlock && block.number <= p.endBlock, "Governor: voting not active");
        require(!p.hasVoted[msg.sender], "Governor: already voted");

        uint256 votes = token.getVotes(msg.sender);
        require(votes > 0, "Governor: no voting power");

        p.hasVoted[msg.sender] = true;

        if (support) {
            p.forVotes += votes;
        } else {
            p.againstVotes += votes;
        }

        emit VoteCast(msg.sender, proposalId, support, votes);
    }

    /// @notice Execute a successful proposal.
    /// @param proposalId The proposal to execute.
    function execute(uint256 proposalId) external nonReentrant {
        Proposal storage p = proposals[proposalId];
        require(block.number > p.endBlock, "Governor: voting not ended");
        require(!p.executed, "Governor: already executed");
        require(!p.canceled, "Governor: canceled");
        require(p.forVotes > p.againstVotes, "Governor: not enough for votes");
        require(p.forVotes >= quorumVotes, "Governor: quorum not met");

        p.executed = true;

        for (uint256 i = 0; i < p.targets.length; i++) {
            (bool success, ) = p.targets[i].call{value: p.values[i]}(p.calldatas[i]);
            require(success, "Governor: call failed");
        }

        emit ProposalExecuted(proposalId);
    }

    /// @notice Cancel a proposal (only proposer).
    /// @param proposalId The proposal to cancel.
    function cancel(uint256 proposalId) external {
        Proposal storage p = proposals[proposalId];
        require(msg.sender == p.proposer, "Governor: not proposer");
        require(!p.executed, "Governor: already executed");

        p.canceled = true;
        emit ProposalCanceled(proposalId);
    }

    /// @notice Get the state of a proposal.
    /// @param proposalId The proposal to check.
    /// @return The current state of the proposal.
    function state(uint256 proposalId) public view returns (ProposalState) {
        Proposal storage p = proposals[proposalId];
        if (p.canceled) return ProposalState.Canceled;
        if (p.executed) return ProposalState.Executed;
        if (block.number <= p.endBlock) {
            if (block.number >= p.startBlock) return ProposalState.Active;
            else return ProposalState.Pending;
        }
        if (p.forVotes <= p.againstVotes || p.forVotes < quorumVotes) return ProposalState.Defeated;
        return ProposalState.Succeeded;
    }
}
