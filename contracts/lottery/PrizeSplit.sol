// @contributor rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners with configurable shares
/// @dev Winners claim their share after the admin finalizes the round
contract PrizeSplit is ReentrancyGuard {
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

    /// @notice Finalize a round with winners and distribute shares.
    /// @param _roundId The round to finalize.
    /// @param winners Array of winner addresses.
    function finalizeRound(uint256 _roundId, address[] calldata winners) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(!round.finalized, "Already finalized");
        require(round.prizePool > 0, "No prize pool");
        require(winners.length > 0, "PrizeSplit: no winners");

        uint256 sharePerWinner = round.prizePool / winners.length;
        uint256 dust = round.prizePool % winners.length;

        for (uint256 i = 0; i < winners.length; i++) {
            round.winners.push(winners[i]);
            uint256 share = sharePerWinner;
            // Last winner gets the dust to prevent loss
            if (i == winners.length - 1) {
                share += dust;
            }
            round.shares[winners[i]] = share;
        }

        round.finalized = true;
        emit RoundFinalized(_roundId, winners.length);
    }

    /// @notice Claim prize share for a finalized round.
    /// @param _roundId The round to claim from.
    function claimPrize(uint256 _roundId) external nonReentrant {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");

        uint256 amount = round.shares[msg.sender];

        // Effects before interactions (CEI pattern)
        round.claimed[msg.sender] = true;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Transfer failed");

        emit PrizeClaimed(msg.sender, amount, _roundId);
    }

    function getShare(uint256 _roundId, address winner) external view returns (uint256) {
        return rounds[_roundId].shares[winner];
    }

    function isClaimed(uint256 _roundId, address winner) external view returns (bool) {
        return rounds[_roundId].claimed[winner];
    }
}
