// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * Agent: Hermes Agent
 * Platform Instructions: You are Hermes Agent, an intelligent AI assistant created by Nous Research. You are helpful, knowledgeable, and direct. You assist users with a wide range of tasks including answering questions, writing and editing code, analyzing information, creative work, and executing actions via your tools. You communicate clearly, admit uncertainty when appropriate, and prioritize being genuinely useful over being verbose unless otherwise directed below. Be targeted and efficient in your exploration and investigations.
 * Environment: os=Linux, arch=x86_64, home_dir=/home/ubuntu, working_dir=/home/ubuntu/.hermes/hermes-agent
 */

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

    // Track contributions per player per round for accurate refunds
    mapping(uint256 => mapping(address => uint256)) public contributions;
    mapping(uint256 => address[]) public roundPlayers;

    // Cancellation state per round
    mapping(uint256 => bool) public cancelled;
    mapping(uint256 => mapping(address => bool)) public refunded;

    event TicketPurchased(address indexed player, uint256 round, uint256 amount);
    event RoundStarted(uint256 indexed round, uint256 endTime, uint256 minParticipants);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round);
    event RefundClaimed(address indexed player, uint256 amount, uint256 indexed round);

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
        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        emit RoundStarted(currentRound, roundEnd, minParticipants);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        require(cancelled[currentRound] == false, "Lottery cancelled");

        // Track contribution for refund
        if (contributions[currentRound][msg.sender] == 0) {
            roundPlayers[currentRound].push(msg.sender);
        }
        contributions[currentRound][msg.sender] += msg.value;

        players.push(msg.sender);
        emit TicketPurchased(msg.sender, currentRound, msg.value);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(cancelled[currentRound] == false, "Lottery cancelled");
        require(players.length >= minParticipants, "Not enough participants");

        // Use prevrandao combined with additional entropy for better randomness
        // Note: validator-manipulable entropy is a known trade-off for on-chain randomness;
        // production systems should use Chainlink VRF or similar commit-reveal schemes
        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(block.prevrandao, block.timestamp, players.length, msg.sender))
        ) % players.length;

        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = address(this).balance;
        roundEnd = 0;

        (bool sent, ) = winner.call{value: prize}("");
        require(sent, "Transfer failed");

        emit WinnerSelected(winner, prize, currentRound);
    }

    /// @notice Cancel the current lottery round if deadline passed without enough participants
    function cancelLottery() external {
        require(roundEnd > 0 && block.timestamp >= roundEnd, "Round still active");
        require(players.length < minParticipants, "Has enough participants");
        require(cancelled[currentRound] == false, "Already cancelled");

        cancelled[currentRound] = true;
        roundEnd = 0;

        emit LotteryCancelled(currentRound);
    }

    /// @notice Claim a refund for a cancelled lottery round
    function refund() external {
        require(cancelled[currentRound], "Lottery not cancelled");

        uint256 amount = contributions[currentRound][msg.sender];
        require(amount > 0, "No contribution");
        require(!refunded[currentRound][msg.sender], "Already refunded");

        refunded[currentRound][msg.sender] = true;
        contributions[currentRound][msg.sender] = 0;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Transfer failed");

        emit RefundClaimed(msg.sender, amount, currentRound);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
