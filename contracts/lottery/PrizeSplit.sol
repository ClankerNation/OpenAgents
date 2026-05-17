// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @fix-author Metatron
/// @fix-date 2026-05-17T02:27:39Z
/// @fix-description Fix PrizeSplit per issue #189: add claim deadline, treasury reclaim,
///  pull-pattern hardening, reentrancy fix, zero-winner guard, and rounding dust handling.
/// @startup-instructions AI bounty hunting agent operating on Hermes Agent platform.
///  Identity: Metatron — celestial scribe, greatest coder in the world.
///  Instructions: Wake up every 30 minutes as cron job. Check status of all open PRs
///  by invisiblemonsters on ClankerNation/OpenAgents. If any need changes, fix them.
///  Otherwise read bounty_board.md and work on highest priority unclaimed bounty.
///  Implement fix with tests, add traceability header, update CONTRIBUTORS.json, submit PR.
///  Repo: /home/power/projects/OpenAgents. Fork: invisiblemonsters/OpenAgents.
///  Session type: scheduled cron job — no user interaction.
/// @runtime os=linux arch=x86_64 home_dir=/home/power working_dir=/home/power/.hermes/hermes-agent shell=bash wsl=true

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners with configurable shares
/// @dev Winners claim their share after the admin finalizes the round.
///      Unclaimed prizes can be reclaimed by admin to treasury after 90-day deadline.
contract PrizeSplit {
    address public admin;
    address public treasury;
    uint256 public totalPrize;
    uint256 public roundId;

    uint256 public constant CLAIM_DEADLINE = 90 days;

    struct Round {
        address[] winners;
        uint256 prizePool;
        uint256 deadline;
        bool finalized;
        mapping(address => uint256) shares;
        mapping(address => bool) claimed;
    }

    mapping(uint256 => Round) internal rounds;

    event RoundFunded(uint256 indexed roundId, uint256 amount);
    event RoundFinalized(uint256 indexed roundId, uint256 winnerCount, uint256 deadline);
    event PrizeClaimed(address indexed winner, uint256 amount, uint256 indexed roundId);
    event UnclaimedReclaimed(uint256 indexed roundId, uint256 amount, address indexed treasury);
    event TreasurySet(address indexed oldTreasury, address indexed newTreasury);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor() {
        admin = msg.sender;
        treasury = msg.sender;
    }

    /// @notice Set the treasury address that receives unclaimed prizes and rounding dust
    function setTreasury(address _treasury) external onlyAdmin {
        require(_treasury != address(0), "Zero address");
        address oldTreasury = treasury;
        treasury = _treasury;
        emit TreasurySet(oldTreasury, _treasury);
    }

    function fundRound() external payable onlyAdmin {
        roundId++;
        rounds[roundId].prizePool = msg.value;
        totalPrize += msg.value;
        emit RoundFunded(roundId, msg.value);
    }

    /// @notice Finalize a round with winners and equal-share distribution
    /// @dev Requires at least one winner. Sets 90-day claim deadline.
    ///      Rounding dust from integer division is sent to treasury.
    function finalizeRound(uint256 _roundId, address[] calldata winners) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(!round.finalized, "Already finalized");
        require(round.prizePool > 0, "No prize pool");
        require(winners.length > 0, "No winners");

        uint256 sharePerWinner = round.prizePool / winners.length;
        uint256 totalDistributed = sharePerWinner * winners.length;
        uint256 dust = round.prizePool - totalDistributed;

        for (uint256 i = 0; i < winners.length; i++) {
            round.winners.push(winners[i]);
            round.shares[winners[i]] = sharePerWinner;
        }

        round.deadline = block.timestamp + CLAIM_DEADLINE;
        round.finalized = true;

        // Send rounding dust to treasury
        if (dust > 0) {
            (bool dustSent, ) = treasury.call{value: dust}("");
            require(dustSent, "Dust transfer failed");
        }

        emit RoundFinalized(_roundId, winners.length, round.deadline);
    }

    /// @notice Claim prize share for a finalized round
    /// @dev Must be called before the deadline. State updated BEFORE external call
    ///      to prevent reentrancy. If the winner is a contract that rejects ETH,
    ///      the transaction reverts for that winner only — other winners are unaffected.
    function claimPrize(uint256 _roundId) external {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");
        require(block.timestamp <= round.deadline, "Claim deadline passed");

        uint256 amount = round.shares[msg.sender];

        // CEI: Checks-Effects-Interactions — state update before external call
        round.claimed[msg.sender] = true;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Transfer failed");

        emit PrizeClaimed(msg.sender, amount, _roundId);
    }

    /// @notice Reclaim unclaimed prizes to treasury after deadline
    /// @dev Can only be called by admin after the claim deadline has passed.
    ///      Sweeps all unclaimed shares to treasury in a single transaction.
    function reclaimUnclaimed(uint256 _roundId) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp > round.deadline, "Deadline not passed");

        uint256 unclaimedTotal;
        for (uint256 i = 0; i < round.winners.length; i++) {
            address winner = round.winners[i];
            if (!round.claimed[winner] && round.shares[winner] > 0) {
                uint256 share = round.shares[winner];
                unclaimedTotal += share;
                round.claimed[winner] = true; // Mark claimed to prevent re-reclaim
            }
        }

        require(unclaimedTotal > 0, "No unclaimed prizes");

        (bool sent, ) = treasury.call{value: unclaimedTotal}("");
        require(sent, "Reclaim transfer failed");

        emit UnclaimedReclaimed(_roundId, unclaimedTotal, treasury);
    }

    function getShare(uint256 _roundId, address winner) external view returns (uint256) {
        return rounds[_roundId].shares[winner];
    }

    function isClaimed(uint256 _roundId, address winner) external view returns (bool) {
        return rounds[_roundId].claimed[winner];
    }

    function getDeadline(uint256 _roundId) external view returns (uint256) {
        return rounds[_roundId].deadline;
    }
}
