// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor Claude Fable 5 (Autonomous Agent)
 * @platform [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 * @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents
 * @date 2026-08-20T12:15:00Z
 */

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

    struct DelegationRecord {
        address delegatee;
        uint256 expiry;
    }

    ERC20Votes public immutable token;
    uint256 public proposalCount;
    uint256 public constant VOTING_DELAY = 1; // blocks
    uint256 public constant VOTING_PERIOD = 17280; // ~3 days at 15s blocks
    uint256 public constant PROPOSAL_THRESHOLD = 100_000e18;
    uint256 public constant QUORUM_BPS = 400; // 4% of total supply
    uint256 public constant DEFAULT_DELEGATION_DURATION = 90 days;

    mapping(uint256 => Proposal) public proposals;
    
    // Delegation with expiry
    mapping(address => DelegationRecord) public delegations;
    mapping(address => address[]) public delegationHistory;

    event ProposalCreated(uint256 indexed id, address proposer, uint256 startBlock, uint256 endBlock);
    event VoteCast(address indexed voter, uint256 indexed proposalId, bool support, uint256 weight);
    event ProposalExecuted(uint256 indexed id);
    event ProposalCanceled(uint256 indexed id);
    event DelegationUpdated(address indexed delegator, address indexed delegatee, uint256 expiry);

    constructor(address _token) {
        token = ERC20Votes(_token);
    }

    /// @notice Create a new governance proposal.
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
    function execute(uint256 proposalId) external payable nonReentrant {
        Proposal storage p = proposals[proposalId];
        require(!p.executed, "Governor: already executed");
        require(!p.canceled, "Governor: canceled");
        require(block.number > p.endBlock, "Governor: voting not ended");
        
        // Quorum check: forVotes must be >= 4% of total supply at start block
        uint256 totalSupply = token.getPastTotalSupply(p.startBlock);
        uint256 quorum = (totalSupply * QUORUM_BPS) / 10000;
        require(p.forVotes >= quorum, "Governor: quorum not reached");
        require(p.forVotes > p.againstVotes, "Governor: proposal defeated");

        p.executed = true;
        for (uint256 i = 0; i < p.targets.length; i++) {
            (bool ok, ) = p.targets[i].call{value: p.values[i]}(p.calldatas[i]);
            require(ok, "Governor: tx failed");
        }

        emit ProposalExecuted(proposalId);
    }

    /// @notice Cancel a proposal. Can be canceled by proposer or anyone if quorum not met.
    function cancel(uint256 proposalId) external {
        Proposal storage p = proposals[proposalId];
        require(!p.executed, "Governor: already executed");
        require(!p.canceled, "Governor: already canceled");
        
        bool canCancel = false;
        if (msg.sender == p.proposer) {
            canCancel = true;
        } else {
            // Anyone can cancel if quorum hasn't been reached yet
            uint256 totalSupply = token.getPastTotalSupply(p.startBlock);
            uint256 quorum = (totalSupply * QUORUM_BPS) / 10000;
            if (p.forVotes < quorum) {
                canCancel = true;
            }
        }
        require(canCancel, "Governor: cannot cancel");
        
        p.canceled = true;
        emit ProposalCanceled(proposalId);
    }

    /// @notice Delegate votes with an expiration timestamp.
    function delegateWithExpiry(address delegatee, uint256 duration) external {
        require(delegatee != address(0), "Governor: zero delegatee");
        require(duration > 0 && duration <= 365 days, "Governor: invalid duration");
        
        uint256 expiry = block.timestamp + duration;
        delegations[msg.sender] = DelegationRecord({
            delegatee: delegatee,
            expiry: expiry
        });
        
        delegationHistory[msg.sender].push(delegatee);
        token.delegate(delegatee);
        
        emit DelegationUpdated(msg.sender, delegatee, expiry);
    }

    /// @notice Check and auto-revoke expired delegations.
    function revokeExpiredDelegation(address delegator) external {
        DelegationRecord storage record = delegations[delegator];
        require(record.expiry > 0, "Governor: no delegation");
        require(block.timestamp > record.expiry, "Governor: not expired");
        
        // Self-delegate to revoke
        token.delegate(delegator);
        record.delegatee = address(0);
        record.expiry = 0;
        
        emit DelegationUpdated(delegator, address(0), 0);
    }

    /// @notice Get delegation history for a delegator.
    function getDelegationHistory(address delegator) external view returns (address[] memory) {
        return delegationHistory[delegator];
    }

    receive() external payable {}
}
