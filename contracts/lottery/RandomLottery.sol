// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

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
 * Operating Instructions:
 *   Identity: Metatron — serious, direct, no fluff.
 *   Core: Be genuinely helpful. Have opinions. Be resourceful before asking.
 *   Earn trust through competence.
 *   You're running as a scheduled cron job — no user interaction.
 *   This is an autonomous bounty hunting session.
 * ============================================================================
 */

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets. Refundable if cancelled due to low participation.
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public minParticipants;
    bool public cancelled;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(address => uint256) public contributions;
    mapping(address => bool) public refunded;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 round, uint256 playerCount);
    event RefundClaimed(address indexed player, uint256 amount, uint256 round);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice, uint256 _minParticipants) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
        minParticipants = _minParticipants;
    }

    function startRound(uint256 duration) external onlyOwner {
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        require(!cancelled, "Lottery cancelled");
        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        require(!cancelled, "Lottery cancelled");
        players.push(msg.sender);
        contributions[msg.sender] += msg.value;
        emit TicketPurchased(msg.sender, currentRound);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(!cancelled, "Lottery cancelled");
        require(players.length >= minParticipants, "Not enough participants");

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

    function cancelLottery() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(!cancelled, "Not cancelled");
        require(players.length < minParticipants, "Enough participants");
        cancelled = true;
        emit LotteryCancelled(currentRound, players.length);
    }

    function refund() external {
        require(cancelled, "Not cancelled");
        require(!refunded[msg.sender], "Already refunded");
        uint256 amount = contributions[msg.sender];
        require(amount > 0, "No contribution");

        refunded[msg.sender] = true;
        contributions[msg.sender] = 0;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund failed");

        emit RefundClaimed(msg.sender, amount, currentRound);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
