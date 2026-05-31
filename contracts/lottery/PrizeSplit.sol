// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners with configurable shares
/// @dev Winners claim their share after the admin finalizes the round
contract PrizeSplit {
    uint256 public constant CLAIM_WINDOW = 90 days;

    address public admin;
    address payable public treasury;
    uint256 public totalPrize;
    uint256 public roundId;

    struct Round {
        address[] winners;
        uint256 prizePool;
        bool finalized;
        uint256 claimDeadline;
        uint256 claimedAmount;
        bool reclaimed;
        mapping(address => uint256) shares;
        mapping(address => bool) claimed;
    }

    mapping(uint256 => Round) internal rounds;

    event RoundFunded(uint256 indexed roundId, uint256 amount);
    event RoundFinalized(uint256 indexed roundId, uint256 winnerCount);
    event PrizeClaimed(address indexed winner, uint256 amount, uint256 indexed roundId);
    event UnclaimedReclaimed(uint256 indexed roundId, uint256 amount, address indexed treasury);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor() {
        admin = msg.sender;
        treasury = payable(msg.sender);
    }

    function fundRound() external payable onlyAdmin {
        roundId++;
        rounds[roundId].prizePool = msg.value;
        totalPrize += msg.value;
        emit RoundFunded(roundId, msg.value);
    }

    // BUG: No zero-winner check — if winners array is empty, the function
    // succeeds silently and the prize pool becomes permanently locked
    function finalizeRound(uint256 _roundId, address[] calldata winners) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(!round.finalized, "Already finalized");
        require(round.prizePool > 0, "No prize pool");

        // BUG: Rounding error loses dust — integer division truncates remainder,
        // so (prizePool % winners.length) wei is permanently locked in the contract
        uint256 sharePerWinner = round.prizePool / winners.length;

        for (uint256 i = 0; i < winners.length; i++) {
            round.winners.push(winners[i]);
            round.shares[winners[i]] = sharePerWinner;
        }

        round.claimDeadline = block.timestamp + CLAIM_WINDOW;
        round.finalized = true;
        emit RoundFinalized(_roundId, winners.length);
    }

    function claimPrize(uint256 _roundId) external {
        _claimPrize(_roundId, payable(msg.sender));
    }

    function claimPrizeTo(uint256 _roundId, address payable recipient) external {
        _claimPrize(_roundId, recipient);
    }

    function reclaimUnclaimed(uint256 _roundId) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp > round.claimDeadline, "Claim period active");
        require(!round.reclaimed, "Already reclaimed");

        uint256 amount = round.prizePool - round.claimedAmount;
        round.reclaimed = true;

        (bool sent, ) = treasury.call{value: amount}("");
        require(sent, "Treasury transfer failed");

        emit UnclaimedReclaimed(_roundId, amount, treasury);
    }

    function getClaimDeadline(uint256 _roundId) external view returns (uint256) {
        return rounds[_roundId].claimDeadline;
    }

    function _claimPrize(uint256 _roundId, address payable recipient) internal {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp <= round.claimDeadline, "Claim period over");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");
        require(recipient != address(0), "Invalid recipient");

        uint256 amount = round.shares[msg.sender];

        round.claimed[msg.sender] = true;
        round.claimedAmount += amount;

        (bool sent, ) = recipient.call{value: amount}("");
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
