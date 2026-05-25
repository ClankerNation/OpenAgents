// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * @generated-by Codex
 * @timestamp 2026-05-25T11:32:46Z
 * @runtime os=Windows, arch=x64, home_dir=C:\Users\tupm96,
 * working_dir=C:\Users\tupm96\Desktop\bounty\OpenAgents, shell=powershell
 * Private platform, system, and developer instructions are not disclosed.
 */

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners with configurable shares.
/// @dev Winners claim their own shares after the admin finalizes the round.
contract PrizeSplit {
    uint256 public constant CLAIM_PERIOD = 90 days;

    address public admin;
    address public treasury;
    uint256 public totalPrize;
    uint256 public roundId;

    struct Round {
        address[] winners;
        uint256 prizePool;
        uint256 remainingPrize;
        uint256 claimDeadline;
        bool finalized;
        mapping(address => uint256) shares;
        mapping(address => bool) claimed;
    }

    mapping(uint256 => Round) internal rounds;

    event RoundFunded(uint256 indexed roundId, uint256 amount);
    event RoundFinalized(uint256 indexed roundId, uint256 winnerCount);
    event PrizeClaimed(address indexed winner, uint256 amount, uint256 indexed roundId);
    event TreasuryUpdated(address indexed previousTreasury, address indexed newTreasury);
    event UnclaimedPrizesReclaimed(uint256 indexed roundId, address indexed treasury, uint256 amount);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor() {
        admin = msg.sender;
        treasury = msg.sender;
    }

    function fundRound() external payable onlyAdmin {
        require(msg.value > 0, "No prize");

        roundId++;
        rounds[roundId].prizePool = msg.value;
        totalPrize += msg.value;

        emit RoundFunded(roundId, msg.value);
    }

    function setTreasury(address _treasury) external onlyAdmin {
        require(_treasury != address(0), "Zero treasury");

        emit TreasuryUpdated(treasury, _treasury);
        treasury = _treasury;
    }

    function finalizeRound(uint256 _roundId, address[] calldata winners) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(!round.finalized, "Already finalized");
        require(round.prizePool > 0, "No prize pool");
        require(winners.length > 0, "No winners");

        uint256 sharePerWinner = round.prizePool / winners.length;

        for (uint256 i = 0; i < winners.length; i++) {
            round.winners.push(winners[i]);
            round.shares[winners[i]] = sharePerWinner;
        }

        round.remainingPrize = round.prizePool;
        round.claimDeadline = block.timestamp + CLAIM_PERIOD;
        round.finalized = true;

        emit RoundFinalized(_roundId, winners.length);
    }

    function claim(uint256 _roundId) public {
        _claim(_roundId, msg.sender);
    }

    function claimPrize(uint256 _roundId) external {
        _claim(_roundId, msg.sender);
    }

    function reclaimUnclaimedPrizes(uint256 _roundId) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp > round.claimDeadline, "Claim period active");

        uint256 amount = round.remainingPrize;
        require(amount > 0, "No unclaimed prizes");

        round.remainingPrize = 0;
        totalPrize -= amount;

        (bool sent, ) = treasury.call{value: amount}("");
        require(sent, "Treasury transfer failed");

        emit UnclaimedPrizesReclaimed(_roundId, treasury, amount);
    }

    function _claim(uint256 _roundId, address winner) internal {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp <= round.claimDeadline, "Claim period ended");
        require(round.shares[winner] > 0, "No share");
        require(!round.claimed[winner], "Already claimed");

        uint256 amount = round.shares[winner];

        round.claimed[winner] = true;
        round.remainingPrize -= amount;
        totalPrize -= amount;

        (bool sent, ) = winner.call{value: amount}("");
        require(sent, "Transfer failed");

        emit PrizeClaimed(winner, amount, _roundId);
    }

    function getShare(uint256 _roundId, address winner) external view returns (uint256) {
        return rounds[_roundId].shares[winner];
    }

    function isClaimed(uint256 _roundId, address winner) external view returns (bool) {
        return rounds[_roundId].claimed[winner];
    }

    function getClaimDeadline(uint256 _roundId) external view returns (uint256) {
        return rounds[_roundId].claimDeadline;
    }

    function getRemainingPrize(uint256 _roundId) external view returns (uint256) {
        return rounds[_roundId].remainingPrize;
    }
}
