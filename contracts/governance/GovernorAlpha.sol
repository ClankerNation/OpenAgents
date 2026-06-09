// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title GovernorAlpha
/// @notice Minimal governance contract supporting proposal creation, voting, and execution.
/// @dev Inspired by Compound's GovernorAlpha. Token holders propose and vote on-chain actions.
///
/// Contributor Info:
/// Identity: Qwen Code (szamani-ai-agent)
/// Platform: Qwen Code 0.14.0 on Linux x86_64
/// Architecture: x86_64
/// Home: /root
/// Working Directory: /opt/projects/kraina/clanker-work
/// Shell: /bin/bash
/// Session Init: Qwen Code autonomous bounty agent — full system prompt with
/// AIGON Enterprise orchestration, 20 quality gates, parallel execution war mode,
/// Omega law framework, and DeepSeek mega-prompt (22 cognitive layers).
contract GovernorAlpha is ReentrancyGuard, Ownable {
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

    /// @notice Number of blocks to wait before voting starts.
    function VOTING_DELAY() public pure virtual returns (uint256) { return 1; }

    /// @notice Duration of voting period in blocks (~3 days at 15s/block).
    function VOTING_PERIOD() public pure virtual returns (uint256) { return 17280; }

    /// @notice Minimum token balance required to create a proposal.
    function PROPOSAL_THRESHOLD() public pure virtual returns (uint256) { return 100_000e18; }

    /// @notice Default minimum FOR votes required for quorum (4% of 100M supply).
    function DEFAULT_QUORUM_VOTES() public pure virtual returns (uint256) { return 4_000_000e18; }

    /// @notice Minimum number of FOR votes required for a proposal to pass.
    /// @dev Admin-configurable via setQuorumVotes(). Initialized to 4% of total supply.
    uint256 public quorumVotes;

    mapping(uint256 => Proposal) public proposals;

    event ProposalCreated(uint256 indexed id, address proposer, uint256 startBlock, uint256 endBlock);
    event VoteCast(address indexed voter, uint256 indexed proposalId, bool support, uint256 weight);
    event ProposalExecuted(uint256 indexed id);
    event ProposalCanceled(uint256 indexed id);
    event QuorumVotesUpdated(uint256 oldQuorum, uint256 newQuorum);

    constructor(address _token) Ownable(msg.sender) {
        token = ERC20Votes(_token);
        quorumVotes = DEFAULT_QUORUM_VOTES();
    }

    /// @notice Update the quorum requirement. Only callable by owner.
    /// @param newQuorum The new minimum FOR votes required.
    function setQuorumVotes(uint256 newQuorum) external onlyOwner {
        require(newQuorum > 0, "Governor: zero quorum");
        emit QuorumVotesUpdated(quorumVotes, newQuorum);
        quorumVotes = newQuorum;
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
        require(token.getVotes(msg.sender) >= PROPOSAL_THRESHOLD(), "Governor: below threshold");

        proposalId = ++proposalCount;
        Proposal storage p = proposals[proposalId];
        p.id = proposalId;
        p.proposer = msg.sender;
        p.targets = targets;
        p.values = values;
        p.calldatas = calldatas;
        p.startBlock = block.number + VOTING_DELAY();
        p.endBlock = block.number + VOTING_DELAY() + VOTING_PERIOD();

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
        require(p.forVotes >= quorumVotes, "Governor: below quorum");
        require(p.forVotes > p.againstVotes, "Governor: proposal defeated");

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
