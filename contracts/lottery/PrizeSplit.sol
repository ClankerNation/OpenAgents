// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title PrizeSplit
 * @notice Distributes prize pool among multiple winners with configurable shares
 * @dev Pull pattern — winners claim individually. Unclaimed prizes reclaimed by admin after 90-day deadline.
 * @contributor Gaotax2006
 * @platform claude-code/opus-4.8
 * @runtime node-v24.15.0 / win32 / amd64
 * @date 2026-06-25
 * @fixes #126 — Pull pattern for individual claiming + deadline for unclaimed prizes
 */
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
        mapping(address => uint256) shares;
        mapping(address => bool) claimed;
    }

    mapping(uint256 => Round) internal rounds;

    event RoundFunded(uint256 indexed roundId, uint256 amount);
    event RoundFinalized(uint256 indexed roundId, uint256 winnerCount);
    event PrizeClaimed(address indexed winner, uint256 amount, uint256 indexed roundId);
    event TreasuryReclaim(uint256 indexed roundId, uint256 amount, address indexed to);

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

        // FIX: Distribute remainder to last winner to avoid dust loss
        uint256 baseShare = round.prizePool / winners.length;
        uint256 remainder = round.prizePool % winners.length;

        for (uint256 i = 0; i < winners.length; i++) {
            round.winners.push(winners[i]);
            round.shares[winners[i]] = baseShare + (i == winners.length - 1 ? remainder : 0);
        }

        round.finalized = true;
        round.deadline = block.timestamp + CLAIM_DEADLINE;
        emit RoundFinalized(_roundId, winners.length);
    }

    // FIX: Pull pattern — winners claim individually
    // FIX: State updated BEFORE external call (reentrancy protection)
    function claimPrize(uint256 _roundId) external {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");
        require(block.timestamp <= round.deadline, "Claim deadline expired");

        uint256 amount = round.shares[msg.sender];

        // FIX: Update state BEFORE external call
        round.claimed[msg.sender] = true;

        (bool sent, ) = msg.sender.call{value: amount}("");
        if (!sent) {
            // Revert so winner can retry later
            revert("Transfer failed — recipient contract rejected ETH");
        }

        emit PrizeClaimed(msg.sender, amount, _roundId);
    }

    // FIX: Admin can reclaim unclaimed prizes after deadline
    function reclaimUnclaimed(uint256 _roundId) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp > round.deadline, "Claim period not expired");

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
        require(sent, "Reclaim failed");

        emit TreasuryReclaim(_roundId, unclaimed, admin);
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
