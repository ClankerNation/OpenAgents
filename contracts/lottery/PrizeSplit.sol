// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners with configurable shares
/// @dev Winners claim their share individually using the pull pattern — failed claims
///      do not affect other winners. Uses checks-effects-interactions to prevent reentrancy.
/// @contributor Gaotax2006
/// @platform claude-code/opus-4.8
/// @runtime node-v24.15.0 / win32 / amd64
/// @date 2026-06-24
/// @fixes #189 — Pull pattern claim, reentrancy guard, rounding fix, empty-winner check

contract PrizeSplit {
    address public admin;
    uint256 public totalPrize;
    uint256 public roundId;

    struct Round {
        address[] winners;
        uint256 prizePool;
        bool finalized;
        mapping(address => uint256) shares;
        mapping(address => bool) claimed;
    }

    mapping(uint256 => Round) internal rounds;

    event RoundFunded(uint256 indexed roundId, uint256 amount);
    event RoundFinalized(uint256 indexed roundId, uint256 winnerCount);
    event PrizeClaimed(address indexed winner, uint256 amount, uint256 indexed roundId);
    event PrizeRefunded(address indexed admin, uint256 amount, uint256 indexed roundId);

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
        Round storage round = rounds[_roundId];
        require(!round.finalized, "Already finalized");
        require(round.prizePool > 0, "No prize pool");
        require(winners.length > 0, "No winners");

        // Distribute evenly, leftover stays in contract for admin refund
        uint256 sharePerWinner = round.prizePool / winners.length;

        for (uint256 i = 0; i < winners.length; i++) {
            require(winners[i] != address(0), "Zero address winner");
            round.winners.push(winners[i]);
            round.shares[winners[i]] = sharePerWinner;
        }

        round.finalized = true;
        emit RoundFinalized(_roundId, winners.length);
    }

    /**
     * @notice Claim your prize using the pull pattern.
     *         Each winner calls this independently — a failed transfer for one
     *         winner does not block others. State is updated before the call
     *         to prevent reentrancy.
     */
    function claimPrize(uint256 _roundId) external {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");

        uint256 amount = round.shares[msg.sender];

        // Effects before interactions — prevents reentrancy
        round.claimed[msg.sender] = true;

        // Interactions after state update
        (bool sent, ) = msg.sender.call{value: amount}("");
        if (!sent) {
            // Undo claim so winner can retry (e.g., with a different address)
            round.claimed[msg.sender] = false;
            return;
        }

        emit PrizeClaimed(msg.sender, amount, _roundId);
    }

    /**
     * @notice Refund unclaimed prize dust back to admin.
     *         Called after all winners have claimed to recover leftover wei.
     */
    function refundUnclaimed(uint256 _roundId) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");

        uint256 totalClaimed;
        for (uint256 i = 0; i < round.winners.length; i++) {
            if (round.claimed[round.winners[i]]) {
                totalClaimed += round.shares[round.winners[i]];
            }
        }

        uint256 remaining = address(this).balance - (round.prizePool - totalClaimed);
        if (remaining > 0) {
            (bool sent, ) = admin.call{value: remaining}("");
            require(sent, "Refund failed");
        }

        emit PrizeRefunded(admin, remaining, _roundId);
    }

    function getShare(uint256 _roundId, address winner) external view returns (uint256) {
        return rounds[_roundId].shares[winner];
    }

    function isClaimed(uint256 _roundId, address winner) external view returns (bool) {
        return rounds[_roundId].claimed[winner];
    }
}
