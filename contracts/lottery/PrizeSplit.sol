// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners with configurable shares
/// @dev Winners claim their share after the admin finalizes the round
contract PrizeSplit {
    address public admin;
    uint256 public totalPrize;
    uint256 public roundId;
    uint256 public constant CLAIM_PERIOD = 90 days;

    struct Round {
        address[] winners;
        uint256 prizePool;
        uint256 reclaimAfter;
        bool finalized;
        mapping(address => uint256) shares;
        mapping(address => bool) claimed;
    }

    mapping(uint256 => Round) internal rounds;

    event RoundFunded(uint256 indexed roundId, uint256 amount);
    event RoundFinalized(uint256 indexed roundId, uint256 winnerCount);
    event PrizeClaimed(address indexed winner, uint256 amount, uint256 indexed roundId);
    event UnclaimedPrizesReclaimed(uint256 indexed roundId, uint256 amount);

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

        // BUG: Rounding error loses dust — integer division truncates remainder,
        // so (prizePool % winners.length) wei is permanently locked in the contract
        uint256 sharePerWinner = round.prizePool / winners.length;

        for (uint256 i = 0; i < winners.length; i++) {
            round.winners.push(winners[i]);
            round.shares[winners[i]] = sharePerWinner;
        }

        round.reclaimAfter = block.timestamp + CLAIM_PERIOD;
        round.finalized = true;
        emit RoundFinalized(_roundId, winners.length);
    }

    function claimPrize(uint256 _roundId) external {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");

        uint256 amount = round.shares[msg.sender];

        round.claimed[msg.sender] = true;
        totalPrize -= amount;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Transfer failed");

        emit PrizeClaimed(msg.sender, amount, _roundId);
    }

    function reclaimUnclaimed(uint256 _roundId) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp >= round.reclaimAfter, "Claim period active");

        uint256 amount;
        for (uint256 i = 0; i < round.winners.length; i++) {
            address winner = round.winners[i];
            if (!round.claimed[winner]) {
                uint256 share = round.shares[winner];
                round.claimed[winner] = true;
                amount += share;
            }
        }

        require(amount > 0, "No unclaimed prizes");
        totalPrize -= amount;

        (bool sent, ) = admin.call{value: amount}("");
        require(sent, "Treasury transfer failed");

        emit UnclaimedPrizesReclaimed(_roundId, amount);
    }

    function getShare(uint256 _roundId, address winner) external view returns (uint256) {
        return rounds[_roundId].shares[winner];
    }

    function isClaimed(uint256 _roundId, address winner) external view returns (bool) {
        return rounds[_roundId].claimed[winner];
    }

    function getReclaimAfter(uint256 _roundId) external view returns (uint256) {
        return rounds[_roundId].reclaimAfter;
    }
}
