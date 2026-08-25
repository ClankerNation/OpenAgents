// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
// @fix-author rafaio1
// @date 2026-08-25T01:55:00Z
// @runtime linux x64 /tmp/openagents_issue_202 bash
// @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement, senior dev multi-agent orchestration, and Wise payout integration.

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners with configurable shares
/// @dev Winners claim their share after the admin finalizes the round

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners with configurable shares
/// @dev Winners claim their share after the admin finalizes the round (pull pattern)
contract PrizeSplit {
    address public admin;
    address public treasury;
    uint256 public totalPrize;
    uint256 public roundId;
    uint256 public constant CLAIM_DEADLINE = 90 days;

    struct Round {
        address[] winners;
        uint256 prizePool;
        uint256 finalizedAt;
        bool finalized;
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

    /// @notice Finalize a round with winner addresses. Shares are split equally.
    /// @dev Dust (remainder from integer division) is assigned to the last winner.
    function finalizeRound(uint256 _roundId, address[] calldata winners) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(!round.finalized, "Already finalized");
        require(round.prizePool > 0, "No prize pool");
        require(winners.length > 0, "No winners");

        uint256 sharePerWinner = round.prizePool / winners.length;
        uint256 dust = round.prizePool % winners.length;

        for (uint256 i = 0; i < winners.length; i++) {
            round.winners.push(winners[i]);
            round.shares[winners[i]] = sharePerWinner;
        }
        // Assign dust to last winner to prevent locked funds
        if (dust > 0) {
            round.shares[winners[winners.length - 1]] += dust;
        }

        round.finalized = true;
        round.finalizedAt = block.timestamp;
        emit RoundFinalized(_roundId, winners.length);
    }

    /// @notice Claim prize via pull pattern. Safe for contract winners without receive().
    function claimPrize(uint256 _roundId) external {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp <= round.finalizedAt + CLAIM_DEADLINE, "Claim deadline passed");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");

        uint256 amount = round.shares[msg.sender];
        // State update BEFORE external call (CEI pattern) to prevent reentrancy
        round.claimed[msg.sender] = true;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Transfer failed");

        emit PrizeClaimed(msg.sender, amount, _roundId);
    }

    /// @notice Reclaim unclaimed prizes after the 90-day deadline. Sends to treasury.
    function reclaimUnclaimed(uint256 _roundId) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp > round.finalizedAt + CLAIM_DEADLINE, "Deadline not passed");

        uint256 unclaimedTotal = 0;
        for (uint256 i = 0; i < round.winners.length; i++) {
            address winner = round.winners[i];
            if (!round.claimed[winner]) {
                unclaimedTotal += round.shares[winner];
                round.claimed[winner] = true; // Mark as claimed to prevent double-spend
            }
        }

        require(unclaimedTotal > 0, "Nothing to reclaim");
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
        uint256 winnerCount
    ) {
        Round storage round = rounds[_roundId];
        return (round.prizePool, round.finalized, round.finalizedAt, round.winners.length);
    }
}
