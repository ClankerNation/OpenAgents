// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Contributor: Gaotax2006
// Platform: warpSpeed, opencode CLI
// Runtime: OS=win32 Arch=x64 Home=C:\Users\asus WorkDir=F:\ai-bounty-work\bounty-hunter\openagents Shell=powershell
// Date: 2026-05-17

contract PrizeSplit {
    address public admin;
    uint256 public totalPrize;
    uint256 public roundId;

    uint256 public constant CLAIM_DEADLINE = 90 days;

    struct Round {
        address[] winners;
        uint256 prizePool;
        bool finalized;
        uint256 deadline;
        uint256 lastShare;
        mapping(address => uint256) shares;
        mapping(address => bool) claimed;
    }

    mapping(uint256 => Round) internal rounds;

    event RoundFunded(uint256 indexed roundId, uint256 amount);
    event RoundFinalized(uint256 indexed roundId, uint256 winnerCount);
    event PrizeClaimed(address indexed winner, uint256 amount, uint256 indexed roundId);
    event UnclaimedSwept(uint256 indexed roundId, uint256 amount);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor() {
        admin = msg.sender;
    }

    function fundRound() external payable onlyAdmin {
        roundId++;
        rounds[roundId].prizePool = msg.value;
        totalPrize += msg.value;
        emit RoundFunded(roundId, msg.value);
    }

    function finalizeRound(uint256 _roundId, address[] calldata winners) external onlyAdmin {
        require(winners.length > 0, "No winners");
        Round storage round = rounds[_roundId];
        require(!round.finalized, "Already finalized");
        require(round.prizePool > 0, "No prize pool");

        uint256 sharePerWinner = round.prizePool / winners.length;
        uint256 dust = round.prizePool - (sharePerWinner * winners.length);

        for (uint256 i = 0; i < winners.length; i++) {
            round.winners.push(winners[i]);
            uint256 share = sharePerWinner;
            if (i == winners.length - 1) {
                share += dust;
            }
            round.shares[winners[i]] = share;
        }

        round.lastShare = sharePerWinner + dust;
        round.deadline = block.timestamp + CLAIM_DEADLINE;
        round.finalized = true;
        emit RoundFinalized(_roundId, winners.length);
    }

    function claimPrize(uint256 _roundId) external {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp < round.deadline, "Claim deadline passed");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");

        uint256 amount = round.shares[msg.sender];
        round.claimed[msg.sender] = true;

        (bool sent, ) = msg.sender.call{value: amount}("");
        if (!sent) {
            round.claimed[msg.sender] = false;
            return;
        }

        emit PrizeClaimed(msg.sender, amount, _roundId);
    }

    function sweepUnclaimed(uint256 _roundId) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp >= round.deadline, "Deadline not passed");
        uint256 remaining = address(this).balance;
        if (remaining > 0) {
            (bool sent, ) = admin.call{value: remaining}("");
            require(sent, "Sweep failed");
        }
        emit UnclaimedSwept(_roundId, remaining);
    }

    function getShare(uint256 _roundId, address winner) external view returns (uint256) {
        return rounds[_roundId].shares[winner];
    }

    function isClaimed(uint256 _roundId, address winner) external view returns (bool) {
        return rounds[_roundId].claimed[winner];
    }
}
