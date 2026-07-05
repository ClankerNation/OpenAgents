// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract GovernorAlpha {
    struct Proposal {
        uint256 id;
        address proposer;
        uint256 forVotes;
        uint256 againstVotes;
        uint256 startBlock;
        uint256 endBlock;
        bool executed;
        bool canceled;
    }
    
    mapping(uint256 => Proposal) public proposals;
    uint256 public quorumVotes = 40000e18;  // 40k tokens
    enum ProposalState { Pending, Active, Canceled, Defeated, Succeeded, Queued, Expired, Executed }
    
    function state(uint256 proposalId) public view returns (ProposalState) {
        Proposal storage p = proposals[proposalId];
        if (p.executed) return ProposalState.Executed;
        if (p.canceled) return ProposalState.Canceled;
        if (block.number < p.startBlock) return ProposalState.Pending;
        if (block.number <= p.endBlock) return ProposalState.Active;
        if (p.forVotes <= p.againstVotes || p.forVotes < quorumVotes) return ProposalState.Defeated;
        return ProposalState.Succeeded;
    }
    
    function execute(uint256 proposalId) external payable {
        require(state(proposalId) == ProposalState.Succeeded, "Not succeeded");
        Proposal storage p = proposals[proposalId];
        // Fix #180: verify quorum was reached
        require(p.forVotes >= quorumVotes, "Quorum not reached");  // FIX
        p.executed = true;
    }
}
