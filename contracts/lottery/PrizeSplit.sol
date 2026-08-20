// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners with configurable shares using pull pattern
/// @dev Winners claim their share individually after the admin finalizes the round.
///      Unclaimed prizes can be reclaimed by treasury after deadline.
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

    /// @notice Finalize a round with winner addresses and equal share distribution.
    /// @param _roundId The round to finalize.
    /// @param winners Array of winner addresses.
    function finalizeRound(uint256 _roundId, address[] calldata winners) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(!round.finalized, "Already finalized");
        require(round.prizePool > 0, "No prize pool");
        require(winners.length > 0, "No winners");

        uint256 sharePerWinner = round.prizePool / winners.length;
        require(sharePerWinner > 0, "Prize too small for winner count");

        for (uint256 i = 0; i < winners.length; i++) {
            round.winners.push(winners[i]);
            round.shares[winners[i]] = sharePerWinner;
        }

        round.finalized = true;
        round.finalizedAt = block.timestamp;
        emit RoundFinalized(_roundId, winners.length);
    }

    /// @notice Claim prize using pull pattern. Each winner claims individually.
    ///         Contract winners that reject ETH don't block other winners.
    /// @param _roundId The round to claim from.
    function claimPrize(uint256 _roundId) external {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");
        require(block.timestamp <= round.finalizedAt + CLAIM_DEADLINE, "Claim deadline passed");

        uint256 amount = round.shares[msg.sender];

        // Update state BEFORE external call to prevent reentrancy
        round.claimed[msg.sender] = true;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Transfer failed");

        emit PrizeClaimed(msg.sender, amount, _roundId);
    }

    /// @notice Reclaim unclaimed prizes after deadline. Only callable by treasury.
    /// @param _roundId The round to reclaim from.
    function reclaimUnclaimed(uint256 _roundId) external {
        require(msg.sender == treasury, "Not treasury");
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp > round.finalizedAt + CLAIM_DEADLINE, "Deadline not passed");

        uint256 unclaimedAmount = 0;
        for (uint256 i = 0; i < round.winners.length; i++) {
            address winner = round.winners[i];
            if (!round.claimed[winner]) {
                unclaimedAmount += round.shares[winner];
                round.claimed[winner] = true; // Mark as claimed to prevent double-reclaim
            }
        }

        require(unclaimedAmount > 0, "Nothing to reclaim");

        (bool sent, ) = treasury.call{value: unclaimedAmount}("");
        require(sent, "Treasury transfer failed");

        emit TreasuryReclaim(_roundId, unclaimedAmount);
    }

    function getShare(uint256 _roundId, address winner) external view returns (uint256) {
        return rounds[_roundId].shares[winner];
    }

    function isClaimed(uint256 _roundId, address winner) external view returns (bool) {
        return rounds[_roundId].claimed[winner];
    }

    function canClaim(uint256 _roundId, address winner) external view returns (bool) {
        Round storage round = rounds[_roundId];
        return round.finalized && 
               round.shares[winner] > 0 && 
               !round.claimed[winner] && 
               block.timestamp <= round.finalizedAt + CLAIM_DEADLINE;
    }
}
