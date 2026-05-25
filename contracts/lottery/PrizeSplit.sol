// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * @fix-author Codex
 * @date 2026-05-25T10:48:59Z
 * @runtime os=Windows, arch=x64,
 * working_dir=C:\Users\tupm96\Desktop\bounty\OpenAgents, shell=powershell
 * Private platform, system, and developer instructions are not disclosed.
 */

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners with configurable shares
/// @dev Winners claim their share after the admin finalizes the round
contract PrizeSplit {
    uint256 public constant CLAIM_PERIOD = 90 days;

    address public admin;
    address public treasury;
    uint256 public totalPrize;
    uint256 public roundId;

    struct Round {
        address[] winners;
        uint256 prizePool;
        uint256 unclaimedPrize;
        uint256 claimDeadline;
        bool finalized;
        mapping(address => uint256) shares;
        mapping(address => bool) claimed;
    }

    mapping(uint256 => Round) internal rounds;

    event RoundFunded(uint256 indexed roundId, uint256 amount);
    event RoundFinalized(uint256 indexed roundId, uint256 winnerCount, uint256 claimDeadline);
    event PrizeClaimed(address indexed winner, uint256 amount, uint256 indexed roundId);
    event ExpiredPrizesReclaimed(uint256 indexed roundId, address indexed treasury, uint256 amount);
    event TreasuryUpdated(address indexed treasury);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor() {
        admin = msg.sender;
        treasury = msg.sender;
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

        uint256 sharePerWinner = round.prizePool / winners.length;
        require(sharePerWinner > 0, "Share too small");

        for (uint256 i = 0; i < winners.length; i++) {
            require(winners[i] != address(0), "Invalid winner");
            require(round.shares[winners[i]] == 0, "Duplicate winner");
            round.winners.push(winners[i]);
            round.shares[winners[i]] = sharePerWinner;
        }

        round.unclaimedPrize = round.prizePool;
        round.claimDeadline = block.timestamp + CLAIM_PERIOD;
        round.finalized = true;
        emit RoundFinalized(_roundId, winners.length, round.claimDeadline);
    }

    function claim(uint256 _roundId) external {
        _claim(_roundId);
    }

    function claimPrize(uint256 _roundId) external {
        _claim(_roundId);
    }

    function reclaimExpiredPrizes(uint256 _roundId) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp > round.claimDeadline, "Claim active");

        uint256 amount = round.unclaimedPrize;
        require(amount > 0, "No unclaimed prize");

        round.unclaimedPrize = 0;
        totalPrize -= amount;

        (bool sent, ) = treasury.call{value: amount}("");
        require(sent, "Treasury transfer failed");

        emit ExpiredPrizesReclaimed(_roundId, treasury, amount);
    }

    function setTreasury(address _treasury) external onlyAdmin {
        require(_treasury != address(0), "Invalid treasury");
        treasury = _treasury;
        emit TreasuryUpdated(_treasury);
    }

    function _claim(uint256 _roundId) internal {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp <= round.claimDeadline, "Claim expired");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");

        uint256 amount = round.shares[msg.sender];

        round.claimed[msg.sender] = true;
        round.shares[msg.sender] = 0;
        round.unclaimedPrize -= amount;
        totalPrize -= amount;

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

    function getClaimDeadline(uint256 _roundId) external view returns (uint256) {
        return rounds[_roundId].claimDeadline;
    }

    function getUnclaimedPrize(uint256 _roundId) external view returns (uint256) {
        return rounds[_roundId].unclaimedPrize;
    }
}
