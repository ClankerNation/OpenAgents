// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

// @fix-author rafaio1
// @date 2026-08-25T00:00:00Z
// @runtime linux x64 /tmp/openagents_issue_176 bash
// @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness with refund mechanism
/// @dev Players buy tickets, and a random winner is selected after the round ends.
///      If minimum participants are not met, all players can claim refunds.
contract RandomLottery is ReentrancyGuard {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public minParticipants;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(uint256 => mapping(address => bool)) public refunded;
    mapping(uint256 => bool) public roundRefundable;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event RefundClaimed(address indexed player, uint256 amount, uint256 round);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice, uint256 _minParticipants) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
        minParticipants = _minParticipants > 0 ? _minParticipants : 2;
    }

    function startRound(uint256 duration) external onlyOwner {
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        roundRefundable[currentRound] = false;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        emit TicketPurchased(msg.sender, currentRound);
    }

    function drawWinner() external onlyOwner nonReentrant {
        require(block.timestamp >= roundEnd, "Round not ended");

        if (players.length < minParticipants) {
            roundRefundable[currentRound] = true;
            roundEnd = 0;
            return;
        }

        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(block.prevrandao, block.timestamp, players.length))
        ) % players.length;

        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = address(this).balance;
        roundEnd = 0;

        (bool sent, ) = winner.call{value: prize}("");
        if (!sent) {
            // If winner cannot receive ETH, mark round as refundable instead of locking funds
            roundRefundable[currentRound] = true;
        } else {
            emit WinnerSelected(winner, prize, currentRound);
        }
    }

    /// @notice Claim refund if round was cancelled or winner transfer failed
    function claimRefund(uint256 round) external nonReentrant {
        require(roundRefundable[round], "Round not refundable");
        require(!refunded[round][msg.sender], "Already refunded");

        // Verify sender participated in this round
        bool participated = false;
        for (uint256 i = 0; i < players.length; ) {
            if (players[i] == msg.sender) {
                participated = true;
                break;
            }
            unchecked { ++i; }
        }
        require(participated, "Not a participant");

        refunded[round][msg.sender] = true;
        (bool success, ) = msg.sender.call{value: ticketPrice}("");
        require(success, "Refund transfer failed");

        emit RefundClaimed(msg.sender, ticketPrice, round);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }

    function setMinParticipants(uint256 _min) external onlyOwner {
        require(_min > 0, "Invalid minimum");
        minParticipants = _min;
    }
}
