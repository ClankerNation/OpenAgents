// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners with configurable shares
/// @dev Winners claim their share individually via pull pattern to prevent
///      contract winners without receive() from blocking other winners.
/// @custom:fix-author Gaotax2006
/// @custom:date 2026-06-23
/// @custom:issue #189 Fix PrizeSplit push-to-pull pattern for contract winners
contract PrizeSplit {
    address public admin;
    uint256 public totalPrize;
    uint256 public roundId;
    uint256 public constant CLAIM_DEADLINE = 90 days;

    struct Round {
        address[] winners;
        uint256 prizePool;
        bool finalized;
        mapping(address => uint256) shares;
        mapping(address => bool) claimed;
        uint256 finalizedAt;
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

        // Distribute remainder evenly to avoid rounding dust loss
        uint256 sharePerWinner = round.prizePool / winners.length;
        uint256 remainder = round.prizePool % winners.length;

        for (uint256 i = 0; i < winners.length; i++) {
            uint256 share = sharePerWinner + (i < remainder ? 1 : 0);
            round.winners.push(winners[i]);
            round.shares[winners[i]] = share;
        }

        round.finalized = true;
        round.finalizedAt = block.timestamp;
        emit RoundFinalized(_roundId, winners.length);
    }

    /// @notice Claim prize via pull pattern — safe for contract winners.
    /// @param _roundId Round to claim from.
    function claimPrize(uint256 _roundId) external {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");

        uint256 amount = round.shares[msg.sender];

        // State updated BEFORE external call — prevents reentrancy
        round.claimed[msg.sender] = true;

        emit PrizeClaimed(msg.sender, amount, _roundId);

        // Safe transfer: use call — if contract rejects, only this winner
        // is affected, not the entire pool
        (bool sent, ) = payable(msg.sender).call{value: amount}("");
        require(sent, "Transfer failed");
    }

    /// @notice Reclaim unclaimed prizes after deadline to treasury.
    /// @param _roundId Round to reclaim from.
    function reclaimUnclaimed(uint256 _roundId) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp > round.finalizedAt + CLAIM_DEADLINE, "Not yet claimed");

        uint256 unclaimed;
        for (uint256 i = 0; i < round.winners.length; i++) {
            address winner = round.winners[i];
            if (!round.claimed[winner] && round.shares[winner] > 0) {
                unclaimed += round.shares[winner];
                round.shares[winner] = 0;
            }
        }

        require(unclaimed > 0, "Nothing to reclaim");

        (bool sent, ) = admin.call{value: unclaimed}("");
        require(sent, "Treasury transfer failed");

        emit TreasuryReclaim(_roundId, unclaimed);
    }

    function getShare(uint256 _roundId, address winner) external view returns (uint256) {
        return rounds[_roundId].shares[winner];
    }

    function isClaimed(uint256 _roundId, address winner) external view returns (bool) {
        return rounds[_roundId].claimed[winner];
    }
}
