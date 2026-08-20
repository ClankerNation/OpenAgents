// @contributor rafaio1
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

    mapping(uint256 => Proposal) public proposals;
    
    // Delegation expiry: delegator -> expiry timestamp (0 = permanent/no delegation)
    mapping(address => uint256) public delegationExpiry;

    event ProposalCreated(uint256 indexed id, address proposer, uint256 startBlock, uint256 endBlock);
    event DelegationExpirySet(address indexed delegator, uint256 expiry);
    event DelegationRevoked(address indexed delegator);
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

    /// @notice Cancel a proposal. Proposer can always cancel; anyone can cancel if voting hasn't started.
    /// @param proposalId The proposal to cancel.
    function cancel(uint256 proposalId) external {
        Proposal storage p = proposals[proposalId];
        require(!p.executed && !p.canceled, "Governor: already finalized");
        
        bool isProposer = msg.sender == p.proposer;
        bool beforeVoting = block.number < p.startBlock;
        
        require(isProposer || beforeVoting, "Governor: only proposer can cancel after voting starts");
        
        p.canceled = true;
        emit ProposalCanceled(proposalId);
    }
    
    /// @notice Set an expiry timestamp for your vote delegation.
    /// @param expiry Unix timestamp after which delegation is considered revoked.
    function setDelegationExpiry(uint256 expiry) external {
        require(expiry > block.timestamp, "Governor: expiry must be future");
        delegationExpiry[msg.sender] = expiry;
        emit DelegationExpirySet(msg.sender, expiry);
    }
    
    /// @notice Revoke delegation expiry (make delegation permanent again).
    function revokeDelegationExpiry() external {
        delegationExpiry[msg.sender] = 0;
        emit DelegationRevoked(msg.sender);
    }
    
    /// @notice Check if a delegator's votes are still valid (not expired).
    /// @param delegator Address to check.
    /// @return True if delegation is active (no expiry or expiry not yet reached).
    function isDelegationActive(address delegator) public view returns (bool) {
        uint256 expiry = delegationExpiry[delegator];
        return expiry == 0 || block.timestamp < expiry;
    }

    receive() external payable {}
}
