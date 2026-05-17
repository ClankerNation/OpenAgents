// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @contributor opencode-gaotax2006
/// @platform You are opencode, an interactive CLI tool...
/// @runtime os=win32 arch=x64 workingdir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
/// @date 2026-05-17T00:00:00Z

interface ICheckpointable {
    function getPriorVotes(address account, uint256 blockNumber) external view returns (uint256);
    function delegates(address account) external view returns (address);
    function delegate(address delegatee) external;
}

contract DelegationSnapshotter {
    struct Checkpoint {
        uint256 fromBlock;
        uint256 votes;
    }

    struct ProposalSnapshot {
        uint256 snapshotBlock;
        mapping(address => Checkpoint) userCheckpoints;
        address[] voters;
        bool exists;
    }

    ICheckpointable public token;
    address public governor;

    mapping(uint256 => mapping(address => uint256)) public votingPowerAtProposal;
    mapping(uint256 => mapping(address => bool)) public hasVotedOnProposal;
    mapping(uint256 => uint256) public proposalSnapshotBlock;
    mapping(uint256 => bool) public proposalSnapshotted;

    event SnapshotTaken(uint256 indexed proposalId, uint256 blockNumber);
    event VotingPowerRecorded(uint256 indexed proposalId, address indexed voter, uint256 power);

    modifier onlyGovernor() {
        require(msg.sender == governor, "Not governor");
        _;
    }

    constructor(address _token, address _governor) {
        require(_token != address(0) && _governor != address(0), "Zero address");
        token = ICheckpointable(_token);
        governor = _governor;
    }

    function snapshotProposal(uint256 proposalId) external onlyGovernor {
        require(!proposalSnapshotted[proposalId], "Already snapshotted");
        proposalSnapshotBlock[proposalId] = block.number;
        proposalSnapshotted[proposalId] = true;
        emit SnapshotTaken(proposalId, block.number);
    }

    function recordVoterPower(uint256 proposalId, address voter) external onlyGovernor {
        require(proposalSnapshotted[proposalId], "Not snapshotted");
        uint256 blockNum = proposalSnapshotBlock[proposalId];
        uint256 power;

        try token.getPriorVotes(voter, blockNum) returns (uint256 priorVotes) {
            power = priorVotes;
        } catch {
            power = 0;
        }

        votingPowerAtProposal[proposalId][voter] = power;
        emit VotingPowerRecorded(proposalId, voter, power);
    }

    function getVotingPower(uint256 proposalId, address voter) external view returns (uint256) {
        require(proposalSnapshotted[proposalId], "Not snapshotted");
        uint256 blockNum = proposalSnapshotBlock[proposalId];

        if (votingPowerAtProposal[proposalId][voter] > 0) {
            return votingPowerAtProposal[proposalId][voter];
        }

        uint256 power;
        try token.getPriorVotes(voter, blockNum) returns (uint256 priorVotes) {
            power = priorVotes;
        } catch {
            power = 0;
        }
        return power;
    }

    function hasVoted(uint256 proposalId, address voter) external view returns (bool) {
        return votingPowerAtProposal[proposalId][voter] > 0 || proposalSnapshotBlock[proposalId] > 0;
    }
}
