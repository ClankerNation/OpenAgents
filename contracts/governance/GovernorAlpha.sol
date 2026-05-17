// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title GovernorAlpha
/// @notice Minimal governance contract supporting proposal creation, voting, and execution.
/// @dev Inspired by Compound's GovernorAlpha. Token holders propose and vote on-chain actions.
/// @contributor opencode-gaotax2006
/// @platform You are opencode, an interactive CLI tool...
/// @runtime os=win32 arch=x64 workingdir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
/// @date 2026-05-18T00:00:00Z
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
    uint256 public constant VOTING_DELAY = 1;
    uint256 public constant VOTING_PERIOD = 17280;
    uint256 public constant PROPOSAL_THRESHOLD = 100_000e18;
    uint256 public constant QUORUM_VOTES = 500_000e18;

    mapping(uint256 => Proposal) public proposals;
    mapping(address => uint256) public delegationExpiry;

    event ProposalCreated(uint256 indexed id, address proposer, uint256 startBlock, uint256 endBlock);
    event VoteCast(address indexed voter, uint256 indexed proposalId, bool support, uint256 weight);
    event ProposalExecuted(uint256 indexed id);
    event ProposalCanceled(uint256 indexed id, address indexed canceller, string reason);
    event DelegationExpirySet(address indexed voter, uint256 expiry);

    constructor(address _token) {
        token = ERC20Votes(_token);
    }

    function setDelegationExpiry(uint256 expiryBlock) external {
        delegationExpiry[msg.sender] = expiryBlock;
        emit DelegationExpirySet(msg.sender, expiryBlock);
    }

    function _isExpired(address voter) internal view returns (bool) {
        uint256 expiry = delegationExpiry[voter];
        return expiry != 0 && block.number > expiry;
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
        require(!_isExpired(msg.sender), "Governor: delegation expired");
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

    function cancelProposal(uint256 proposalId) external {
        Proposal storage p = proposals[proposalId];
        require(!p.executed && !p.canceled, "Governor: already finalized");
        require(block.number < p.endBlock, "Governor: voting ended");
        require(
            msg.sender == p.proposer || p.forVotes < p.againstVotes,
            "Governor: not proposer or not defeated"
        );
        p.canceled = true;
        emit ProposalCanceled(proposalId, msg.sender, "Cancelled before quorum");
    }

    function cancel(uint256 proposalId) external {
        Proposal storage p = proposals[proposalId];
        require(msg.sender == p.proposer, "Governor: not proposer");
        require(!p.executed, "Governor: already executed");
        require(block.number < p.endBlock, "Governor: voting ended");
        require(p.forVotes < QUORUM_VOTES, "Governor: quorum reached");
        p.canceled = true;
        emit ProposalCanceled(proposalId, msg.sender, "Cancelled by proposer");
    }

    receive() external payable {}
}
