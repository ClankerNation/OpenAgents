// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title GovernorAlpha
/// @notice Minimal governance contract supporting proposal creation, voting, and execution.
/// @dev Inspired by Compound's GovernorAlpha. Token holders propose and vote on-chain actions.
/// @contributor Gaotax2006
/// @platform Claude Code
/// @runtime Windows 11 Home China, x86_64, F:\\ai-bounty-work\\bounty-hunter
/// @date 2026-06-24T00:00:00Z
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

    // Quorum: configurable minimum votes required for execution
    uint256 public quorumVotes;
    uint256 public constant QUORUM_PERCENTAGE = 4; // 4% of total supply

    address public admin;

    event AdminChanged(address indexed previousAdmin, address indexed newAdmin);
    
    mapping(uint256 => Proposal) public proposals;

    event ProposalCreated(uint256 indexed id, address proposer, uint256 startBlock, uint256 endBlock);
    event VoteCast(address indexed voter, uint256 indexed proposalId, bool support, uint256 weight);
    event ProposalExecuted(uint256 indexed id);
    event ProposalCanceled(uint256 indexed id);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor(ERC20Votes _token) {
        token = _token;
        admin = msg.sender;
        quorumVotes = (token.totalSupply() * QUORUM_PERCENTAGE) / 100;
    }

    function createProposal(
        address[] memory _targets,
        uint256[] memory _values,
        bytes[] memory _calldatas
    ) external {
        require(token.getPriorVotes(msg.sender, block.number - 1) >= PROPOSAL_THRESHOLD, "Below threshold");

        proposalCount++;
        Proposal storage p = proposals[proposalCount];
        p.id = proposalCount;
        p.proposer = msg.sender;
        p.targets = _targets;
        p.values = _values;
        p.calldatas = _calldatas;
        p.startBlock = block.number + VOTING_DELAY;
        p.endBlock = p.startBlock + VOTING_PERIOD;

        emit ProposalCreated(proposalCount, msg.sender, p.startBlock, p.endBlock);
    }

    function castVote(uint256 proposalId, bool support) external {
        Proposal storage p = proposals[proposalId];
        require(p.startBlock <= block.number && block.number <= p.endBlock, "Vote not active");
        require(!p.hasVoted[msg.sender], "Already voted");

        p.hasVoted[msg.sender] = true;
        uint256 weight = token.getPriorVotes(msg.sender, p.startBlock - 1);
        if (support) {
            p.forVotes += weight;
        } else {
            p.againstVotes += weight;
        }

        emit VoteCast(msg.sender, proposalId, support, weight);
    }

    function getState(uint256 proposalId) public view returns (ProposalState) {
        Proposal storage p = proposals[proposalId];

        if (block.number <= p.startBlock) return ProposalState.Pending;
        if (block.number > p.endBlock && p.forVotes < p.againstVotes) return ProposalState.Defeated;
        if (p.executed) return ProposalState.Executed;
        if (p.canceled) return ProposalState.Canceled;

        if (p.forVotes >= p.againstVotes && block.number > p.endBlock) {
            return ProposalState.Succeeded;
        }

        return ProposalState.Active;
    }

    function executeProposal(uint256 proposalId) external nonReentrant {
        Proposal storage p = proposals[proposalId];
        require(getState(proposalId) == ProposalState.Succeeded, "Cannot execute");
        
        // Quorum check: forVotes must meet minimum quorum requirement
        require(p.forVotes >= quorumVotes, "Quorum not met");
        
        require(!p.executed, "Already executed");

        p.executed = true;
        for (uint i = 0; i < p.targets.length; i++) {
            (bool success, ) = p.targets[i].call{value: p.values[i]}(p.calldatas[i]);
            require(success, "Call failed");
        }

        emit ProposalExecuted(proposalId);
    }

    function cancelProposal(uint256 proposalId) external onlyAdmin {
        Proposal storage p = proposals[proposalId];
        require(getState(proposalId) == ProposalState.Pending || getState(proposalId) == ProposalState.Active, "Cannot cancel");
        require(!p.canceled, "Already canceled");

        p.canceled = true;
        emit ProposalCanceled(proposalId);
    }

    function setQuorum(uint256 _quorumVotes) external onlyAdmin {
        require(_quorumVotes <= token.totalSupply() / 2, "Quorum too high");
        quorumVotes = _quorumVotes;
    }

    function getQuorum() external view returns (uint256) {
        return quorumVotes;
    }
}
