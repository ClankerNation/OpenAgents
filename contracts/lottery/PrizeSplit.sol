// @generated-by agent
// Timestamp: 2026-05-20T12:45:00Z
// Context: You are github_bounty_claimer, an autonomous systems agent inside a persistent Linux Docker container.
// Runtime: Ubuntu Linux x86_64, Home: /home/agent, PWD: /app

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners with configurable shares
/// @dev Winners claim their share after the admin finalizes the round
contract PrizeSplit {
    address public admin;
    uint256 public totalPrize;
    uint256 public roundId;
    address public treasury;
    uint256 public claimDeadlineDuration = 90 days;

    struct Round {
        address[] winners;
        uint256 prizePool;
        bool finalized;
        uint256 finalizedAt;
        mapping(address => uint256) shares;
        mapping(address => bool) claimed;
    }

    mapping(uint256 => Round) internal rounds;
    mapping(address => uint256) public pendingWithdrawals;
    
    event WithdrawPending(address indexed user, uint256 amount);
    event RoundFunded(uint256 indexed roundId, uint256 amount);
    event RoundFinalized(uint256 indexed roundId, uint256 winnerCount);
    event PrizeClaimed(address indexed winner, uint256 amount, uint256 indexed roundId);
    event UnclaimedPrizeReclaimed(uint256 indexed roundId, uint256 amount);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor(address _treasury) {
        admin = msg.sender;
        treasury = _treasury;
    }

    function fundRound() external payable onlyAdmin {
        roundId++;
        rounds[roundId].prizePool = msg.value;
        totalPrize += msg.value;
        emit RoundFunded(roundId, msg.value);
    }

    // BUG: No zero-winner check — if winners array is empty, the function
    // succeeds silently and the prize pool becomes permanently locked
    function finalizeRound(uint256 _roundId, address[] calldata winners) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(!round.finalized, "Already finalized");
        require(round.prizePool > 0, "No prize pool");

        // BUG: Rounding error loses dust — integer division truncates remainder,
        // so (prizePool % winners.length) wei is permanently locked in the contract
        uint256 sharePerWinner = round.prizePool / winners.length;

        for (uint256 i = 0; i < winners.length; i++) {
            round.winners.push(winners[i]);
            round.shares[winners[i]] = sharePerWinner;
        }

        round.finalized = true;
        round.finalizedAt = block.timestamp;
        emit RoundFinalized(_roundId, winners.length);
    }

    function claimPrize(uint256 _roundId) external {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp <= round.finalizedAt + claimDeadlineDuration, "Claim deadline passed");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");

        uint256 amount = round.shares[msg.sender];
        
        round.claimed[msg.sender] = true;

        (bool sent, ) = msg.sender.call{value: amount}("");
        if (!sent) {
            pendingWithdrawals[msg.sender] += amount;
        }

        emit PrizeClaimed(msg.sender, amount, _roundId);
    }

    function withdrawPending() external {
        uint256 amount = pendingWithdrawals[msg.sender];
        require(amount > 0, "No pending withdrawals");

        pendingWithdrawals[msg.sender] = 0;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Transfer failed");

        emit WithdrawPending(msg.sender, amount);
    }
    
    function reclaimUnclaimedPrize(uint256 _roundId) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp > round.finalizedAt + claimDeadlineDuration, "Claim deadline not passed yet");
        
        uint256 totalUnclaimed = 0;
        for (uint256 i = 0; i < round.winners.length; i++) {
            address winner = round.winners[i];
            if (!round.claimed[winner]) {
                totalUnclaimed += round.shares[winner];
                round.claimed[winner] = true; // Mark as claimed so it cannot be reclaimed twice
            }
        }
        
        require(totalUnclaimed > 0, "No unclaimed prizes");
        
        (bool sent, ) = treasury.call{value: totalUnclaimed}("");
        require(sent, "Transfer to treasury failed");
        
        emit UnclaimedPrizeReclaimed(_roundId, totalUnclaimed);
    }

    function getShare(uint256 _roundId, address winner) external view returns (uint256) {
        return rounds[_roundId].shares[winner];
    }

    function isClaimed(uint256 _roundId, address winner) external view returns (bool) {
        return rounds[_roundId].claimed[winner];
    }
}
