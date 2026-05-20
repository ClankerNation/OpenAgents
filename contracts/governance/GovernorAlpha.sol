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

    struct Delegation {
        address delegatee;
        uint256 expiry;
    }

    struct DelegationHistoryEntry {
        address delegator;
        address delegatee;
        uint256 expiry;
        uint256 timestamp;
        bool revoked;
    }

    ERC20Votes public immutable token;
    uint256 public proposalCount;
    uint256 public constant VOTING_DELAY = 1; // blocks
    uint256 public constant VOTING_PERIOD = 17280; // ~3 days at 15s blocks
    uint256 public constant PROPOSAL_THRESHOLD = 100_000e18;
    uint256 public constant QUORUM_VOTES = 400_000e18;

    mapping(uint256 => Proposal) public proposals;
    mapping(address => Delegation) public delegations;
    mapping(address => DelegationHistoryEntry[]) private delegationHistory;

    event ProposalCreated(uint256 indexed id, address proposer, uint256 startBlock, uint256 endBlock);
    event VoteCast(address indexed voter, uint256 indexed proposalId, bool support, uint256 weight);
    event ProposalExecuted(uint256 indexed id);
    event ProposalCanceled(uint256 indexed id);
    event DelegationSet(address indexed delegator, address indexed delegatee, uint256 expiry);
    event DelegationRevoked(address indexed delegator, address indexed delegatee, uint256 timestamp);

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
        require(!p.canceled, "Governor: proposal canceled");
        require(block.number >= p.startBlock && block.number <= p.endBlock, "Governor: voting closed");
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
        require(!p.canceled, "Governor: proposal canceled");
        require(!p.executed, "Governor: already executed");
        require(block.number > p.endBlock, "Governor: voting not ended");
        require(p.forVotes > p.againstVotes, "Governor: proposal defeated");

        p.executed = true;
        for (uint256 i = 0; i < p.targets.length; i++) {
            (bool ok, ) = p.targets[i].call{value: p.values[i]}(p.calldatas[i]);
            require(ok, "Governor: tx failed");
        }

        emit ProposalExecuted(proposalId);
    }

    /// @notice Backward-compatible alias for cancelProposal.
    /// @param proposalId The proposal to cancel.
    function cancel(uint256 proposalId) external {
        cancelProposal(proposalId);
    }

    /// @notice Cancel a proposal before quorum is reached.
    /// @param proposalId The proposal to cancel.
    function cancelProposal(uint256 proposalId) public {
        Proposal storage p = proposals[proposalId];
        require(p.id != 0, "Governor: unknown proposal");
        require(!p.canceled, "Governor: already canceled");
        require(!p.executed, "Governor: already executed");
        require(!_quorumReached(p), "Governor: quorum reached");

        p.canceled = true;
        emit ProposalCanceled(proposalId);
    }

    /// @notice Store a governance delegation with an expiry timestamp.
    /// @param delegatee Address receiving delegation.
    /// @param expiry Unix timestamp when the delegation expires.
    function delegateWithExpiry(address delegatee, uint256 expiry) external {
        require(delegatee != address(0), "Governor: zero delegatee");
        require(expiry > block.timestamp, "Governor: expiry elapsed");

        delegations[msg.sender] = Delegation({delegatee: delegatee, expiry: expiry});
        delegationHistory[msg.sender].push(
            DelegationHistoryEntry({
                delegator: msg.sender,
                delegatee: delegatee,
                expiry: expiry,
                timestamp: block.timestamp,
                revoked: false
            })
        );

        emit DelegationSet(msg.sender, delegatee, expiry);
    }

    /// @notice Return the active delegatee, or address(0) after expiry.
    function currentDelegate(address delegator) public view returns (address) {
        Delegation storage delegation = delegations[delegator];
        if (delegation.expiry <= block.timestamp) {
            return address(0);
        }
        return delegation.delegatee;
    }

    /// @notice Clear an expired delegation and write a revocation history entry.
    function revokeExpiredDelegation(address delegator) public {
        Delegation memory delegation = delegations[delegator];
        require(delegation.delegatee != address(0), "Governor: no delegation");
        require(delegation.expiry <= block.timestamp, "Governor: delegation active");

        delete delegations[delegator];
        delegationHistory[delegator].push(
            DelegationHistoryEntry({
                delegator: delegator,
                delegatee: delegation.delegatee,
                expiry: delegation.expiry,
                timestamp: block.timestamp,
                revoked: true
            })
        );

        emit DelegationRevoked(delegator, delegation.delegatee, block.timestamp);
    }

    function delegationHistoryLength(address delegator) external view returns (uint256) {
        return delegationHistory[delegator].length;
    }

    function getDelegationHistory(
        address delegator,
        uint256 index
    ) external view returns (DelegationHistoryEntry memory) {
        return delegationHistory[delegator][index];
    }

    function state(uint256 proposalId) public view returns (ProposalState) {
        Proposal storage p = proposals[proposalId];
        require(p.id != 0, "Governor: unknown proposal");
        if (p.canceled) return ProposalState.Canceled;
        if (p.executed) return ProposalState.Executed;
        if (block.number < p.startBlock) return ProposalState.Pending;
        if (block.number <= p.endBlock) return ProposalState.Active;
        if (p.forVotes <= p.againstVotes) return ProposalState.Defeated;
        return ProposalState.Succeeded;
    }

    function quorumReached(uint256 proposalId) external view returns (bool) {
        Proposal storage p = proposals[proposalId];
        require(p.id != 0, "Governor: unknown proposal");
        return _quorumReached(p);
    }

    function _quorumReached(Proposal storage p) internal view returns (bool) {
        return p.forVotes + p.againstVotes >= QUORUM_VOTES;
    }

    receive() external payable {}
}
