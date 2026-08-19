// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * @fix-author ARO-Agentic | 2026-08-19
 * @runtime os=linux arch=x64 working_dir=/tmp/OpenAgents shell=bash
 */

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners with configurable shares
/// @dev Winners claim their share after the admin finalizes the round
contract PrizeSplit {
    address public admin;
    address public treasury;
    uint256 public totalPrize;
    uint256 public roundId;
    uint256 public constant CLAIM_PERIOD = 90 days;

    struct Round {
        address[] winners;
        uint256 prizePool;
        uint256 finalizedAt;
        bool finalized;
        bool reclaimed;
        mapping(address => uint256) shares;
        mapping(address => bool) claimed;
    }

    mapping(uint256 => Round) internal rounds;

    event RoundFunded(uint256 indexed roundId, uint256 amount);
    event RoundFinalized(uint256 indexed roundId, uint256 winnerCount);
    event PrizeClaimed(address indexed winner, address indexed recipient, uint256 amount, uint256 indexed roundId);
    event TreasuryReclaimed(uint256 indexed roundId, uint256 amount);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor(address _treasury) {
        admin = msg.sender;
        treasury = _treasury;
    }

    function setTreasury(address _treasury) external onlyAdmin {
        treasury = _treasury;
    }

    function fundRound() external payable onlyAdmin {
        roundId++;
        rounds[roundId].prizePool = msg.value;
        totalPrize += msg.value;
        emit RoundFunded(roundId, msg.value);
    }

    function finalizeRound(uint256 _roundId, address[] calldata winners) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(!round.finalized, "Already finalized");
        require(round.prizePool > 0, "No prize pool");
        require(winners.length > 0, "No winners");

        uint256 sharePerWinner = round.prizePool / winners.length;
        require(sharePerWinner > 0, "Prize too small");

        for (uint256 i = 0; i < winners.length; i++) {
            round.winners.push(winners[i]);
            round.shares[winners[i]] = sharePerWinner;
        }

        round.finalized = true;
        round.finalizedAt = block.timestamp;
        emit RoundFinalized(_roundId, winners.length);
    }

    function claimPrize(uint256 _roundId, address recipient) external {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");
        require(block.timestamp <= round.finalizedAt + CLAIM_PERIOD, "Claim period expired");

        uint256 amount = round.shares[msg.sender];
        
        // Effects before interactions (CEI pattern to prevent reentrancy)
        round.claimed[msg.sender] = true;

        (bool sent, ) = recipient.call{value: amount}("");
        require(sent, "Transfer failed");

        emit PrizeClaimed(msg.sender, recipient, amount, _roundId);
    }

    function reclaimUnclaimed(uint256 _roundId) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(!round.reclaimed, "Already reclaimed");
        require(block.timestamp > round.finalizedAt + CLAIM_PERIOD, "Claim period not expired");

        uint256 unclaimedAmount = 0;
        for (uint256 i = 0; i < round.winners.length; i++) {
            address winner = round.winners[i];
            if (!round.claimed[winner]) {
                unclaimedAmount += round.shares[winner];
                round.claimed[winner] = true; // Prevent them from claiming later
            }
        }

        round.reclaimed = true;

        if (unclaimedAmount > 0) {
            (bool sent, ) = treasury.call{value: unclaimedAmount}("");
            require(sent, "Treasury transfer failed");
            emit TreasuryReclaimed(_roundId, unclaimedAmount);
        }
    }

    function getShare(uint256 _roundId, address winner) external view returns (uint256) {
        return rounds[_roundId].shares[winner];
    }

    function isClaimed(uint256 _roundId, address winner) external view returns (bool) {
        return rounds[_roundId].claimed[winner];
    }
    
    receive() external payable {}
}
