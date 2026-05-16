/*
 * ============================================================================
 * CONTRIBUTOR TRACEABILITY HEADER — Autonomous Agent Submission
 * ============================================================================
 * Agent: Metatron (AI — celestial scribe, autonomous coding agent)
 * Platform: Hermes Agent v0.13.0 with DeepSeek V4 Pro model
 *
 * Environment:
 *   OS:      WSL2 Ubuntu 24.04 (Windows Subsystem for Linux)
 *   Arch:    x86_64
 *   Home:    /home/power
 *   Workdir: /home/power/projects/OpenAgents
 *   User:    power (sudo)
 *
 * Operating Instructions (abridged — full SOUL.md/USER.md/AGENTS.md on request):
 *   Identity: Metatron — serious, direct, no fluff.
 *   Core: Be genuinely helpful. Have opinions. Be resourceful before asking.
 *   Earn trust through competence. Remember you're a guest.
 *
 * Task: #176 — Fix RandomLottery refund mechanism missing when lottery cancelled
 * ============================================================================
 */

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends.
///      If minimum participants aren't met by deadline, lottery can be cancelled
///      and participants refunded.
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public minParticipants;
    bool public cancelled;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(uint256 => mapping(address => uint256)) public contributions;
    mapping(uint256 => mapping(address => bool)) public refunded;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round);
    event Refunded(address indexed player, uint256 amount, uint256 round);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    /// @param _ticketPrice Cost per ticket in wei
    /// @param _minParticipants Minimum players required; below this, lottery is cancellable
    constructor(uint256 _ticketPrice, uint256 _minParticipants) {
        require(_minParticipants > 0, "Min participants must be > 0");
        owner = msg.sender;
        ticketPrice = _ticketPrice;
        minParticipants = _minParticipants;
    }

    /// @notice Start a new lottery round
    /// @param duration Seconds until the round ends
    function startRound(uint256 duration) external onlyOwner {
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        cancelled = false;
        emit RoundStarted(currentRound, roundEnd);
    }

    /// @notice Buy a ticket for the current round
    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        require(!cancelled, "Lottery cancelled");
        players.push(msg.sender);
        contributions[currentRound][msg.sender] += msg.value;
        emit TicketPurchased(msg.sender, currentRound);
    }

    /// @notice Draw a winner — requires minParticipants met
    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(!cancelled, "Lottery cancelled");
        require(players.length >= minParticipants, "Not enough participants -- cancel instead");

        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(block.prevrandao, block.timestamp))
        ) % players.length;

        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = address(this).balance;
        roundEnd = 0;

        (bool sent, ) = winner.call{value: prize}("");
        require(sent, "Transfer failed");

        emit WinnerSelected(winner, prize, currentRound);
    }

    /// @notice Cancel the lottery if deadline passed with insufficient participants
    /// @dev Anyone can call this once the round has ended and minParticipants not met
    function cancelLottery() external {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(!cancelled, "Already cancelled");
        require(players.length < minParticipants, "Enough participants -- use drawWinner");

        cancelled = true;
        emit LotteryCancelled(currentRound);
    }

    /// @notice Refund ticket price after lottery is cancelled
    function refund() external {
        require(cancelled, "Not cancelled");
        uint256 round = currentRound;
        uint256 amount = contributions[round][msg.sender];
        require(amount > 0, "No contribution to refund");
        require(!refunded[round][msg.sender], "Already refunded");

        refunded[round][msg.sender] = true;
        contributions[round][msg.sender] = 0;

        (bool sent, ) = payable(msg.sender).call{value: amount}("");
        require(sent, "Refund transfer failed");

        emit Refunded(msg.sender, amount, round);
    }

    /// @notice Get list of players in current round
    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    /// @notice Get current contract balance
    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
