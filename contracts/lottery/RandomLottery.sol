// SPDX-License-Identifier: MIT
// Contributor: Szamani AI
// Platform Instructions: You are the Qwen Code assistant running in AIGON Enterprise production mode. Your task is to fix the RandomLottery contract to support cancellation and refunds. Follow all bounty issue requirements exactly. Do not add unrelated changes. All code must compile with Solidity 0.8.20.
// Runtime: os=linux, arch=x86_64, home_dir=/root, working_dir=/opt/projects/clanker-work-176, shell=bash
pragma solidity ^0.8.20;

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends.
///      Includes cancellation and refund mechanism if minimum participants not met by deadline.
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public minParticipants;

    address[] public players;
    mapping(uint256 => address) public roundWinners;

    // Per-round, per-address contribution tracking for accurate refunds
    mapping(uint256 => mapping(address => uint256)) public contributions;

    // Cancellation state per round
    mapping(uint256 => bool) public cancelled;

    // Refund tracking to prevent double-refund
    mapping(uint256 => mapping(address => bool)) public refundClaimed;

    event TicketPurchased(address indexed player, uint256 round, uint256 amount);
    event RoundStarted(uint256 indexed round, uint256 endTime, uint256 minParticipants);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round);
    event RefundClaimed(address indexed player, uint256 amount, uint256 indexed round);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
    }

    function startRound(uint256 duration, uint256 _minParticipants) external onlyOwner {
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        minParticipants = _minParticipants;
        cancelled[currentRound] = false;
        emit RoundStarted(currentRound, roundEnd, minParticipants);
    }

    function buyTicket() external payable {
        require(!cancelled[currentRound], "Round cancelled");
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        contributions[currentRound][msg.sender] += msg.value;
        emit TicketPurchased(msg.sender, currentRound, msg.value);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(!cancelled[currentRound], "Round cancelled");
        require(players.length >= minParticipants, "Below minimum participants");

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

    /// @notice Cancel the current round if deadline passed and minimum participants not met.
    ///         Can only be called once per round.
    function cancelLottery() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round still active");
        require(players.length < minParticipants, "Minimum participants met - draw instead");
        require(!cancelled[currentRound], "Already cancelled");

        cancelled[currentRound] = true;
        roundEnd = 0;

        emit LotteryCancelled(currentRound);
    }

    /// @notice Refund a participant's contribution after the lottery is cancelled.
    ///         Prevents double-refund by clearing the contribution on claim.
    function refund() external {
        require(cancelled[currentRound], "Not cancelled");
        require(!refundClaimed[currentRound][msg.sender], "Already refunded");
        require(contributions[currentRound][msg.sender] > 0, "No contribution");

        uint256 amount = contributions[currentRound][msg.sender];
        contributions[currentRound][msg.sender] = 0;
        refundClaimed[currentRound][msg.sender] = true;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund transfer failed");

        emit RefundClaimed(msg.sender, amount, currentRound);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
