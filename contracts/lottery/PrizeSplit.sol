// @fix-author rafaio1
// @date 2026-08-25T06:50:00Z
// @runtime linux x64 /tmp/openagents_issue_189 bash
// @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement for PrizeSplit pull pattern and claim deadline (Issue #189)
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners using pull payment pattern
/// @dev Winners claim individually; unclaimed prizes revert to treasury after deadline
contract PrizeSplit {
    address public admin;
    address public treasury;
    uint256 public totalPrize;
    uint256 public roundId;

    /// @notice Duration after finalization during which winners can claim. Default: 90 days.
    uint256 public constant CLAIM_DEADLINE = 90 days;

    struct Round {
        address[] winners;
        uint256 prizePool;
        uint256 finalizedAt;
        bool finalized;
        bool treasuryReclaimed;
        mapping(address => uint256) shares;
        mapping(address => bool) claimed;
    }

    mapping(uint256 => Round) internal rounds;

    event RoundFunded(uint256 indexed roundId, uint256 amount);
    event RoundFinalized(uint256 indexed roundId, uint256 winnerCount);
    event PrizeClaimed(address indexed winner, uint256 amount, uint256 indexed roundId);
    event TreasuryReclaim(uint256 indexed roundId, uint256 amount);

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

    /// @notice Finalize a round by assigning equal shares to each winner.
    /// @param _roundId The round to finalize.
    /// @param winners Array of winner addresses (must not be empty).
    function finalizeRound(uint256 _roundId, address[] calldata winners) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(!round.finalized, "Already finalized");
        require(round.prizePool > 0, "No prize pool");
        require(winners.length > 0, "No winners");

        uint256 sharePerWinner = round.prizePool / winners.length;
        require(sharePerWinner > 0, "Share too small");

        for (uint256 i = 0; i < winners.length; i++) {
            require(winners[i] != address(0), "Zero address winner");
            round.winners.push(winners[i]);
            round.shares[winners[i]] = sharePerWinner;
        }

        round.finalized = true;
        round.finalizedAt = block.timestamp;
        emit RoundFinalized(_roundId, winners.length);
    }

    /// @notice Claim prize using pull pattern. Safe for contract winners without receive().
    /// @param _roundId The round to claim from.
    function claimPrize(uint256 _roundId) external {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp <= round.finalizedAt + CLAIM_DEADLINE, "Claim period expired");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");

        uint256 amount = round.shares[msg.sender];

        // FIX: Update state BEFORE external call to prevent reentrancy
        round.claimed[msg.sender] = true;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Transfer failed");

        emit PrizeClaimed(msg.sender, amount, _roundId);
    }

    /// @notice Reclaim unclaimed prizes to treasury after claim deadline expires.
    /// @param _roundId The round to reclaim from.
    function reclaimToTreasury(uint256 _roundId) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp > round.finalizedAt + CLAIM_DEADLINE, "Claim period not expired");
        require(!round.treasuryReclaimed, "Already reclaimed");

        uint256 unclaimedTotal = 0;
        for (uint256 i = 0; i < round.winners.length; i++) {
            if (!round.claimed[round.winners[i]]) {
                unclaimedTotal += round.shares[round.winners[i]];
                // Mark as claimed so no late claims after treasury reclaim
                round.claimed[round.winners[i]] = true;
            }
        }

        require(unclaimedTotal > 0, "Nothing to reclaim");
        round.treasuryReclaimed = true;

        (bool sent, ) = treasury.call{value: unclaimedTotal}("");
        require(sent, "Treasury transfer failed");

        emit TreasuryReclaim(_roundId, unclaimedTotal);
    }

    function getShare(uint256 _roundId, address winner) external view returns (uint256) {
        return rounds[_roundId].shares[winner];
    }

    function isClaimed(uint256 _roundId, address winner) external view returns (bool) {
        return rounds[_roundId].claimed[winner];
    }

    function getRoundInfo(uint256 _roundId) external view returns (
        uint256 prizePool,
        bool finalized,
        uint256 finalizedAt,
        bool treasuryReclaimed,
        uint256 winnerCount
    ) {
        Round storage round = rounds[_roundId];
        return (
            round.prizePool,
            round.finalized,
            round.finalizedAt,
            round.treasuryReclaimed,
            round.winners.length
        );
    }
}
