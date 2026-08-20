// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness with refund mechanism
/// @dev Players buy tickets, and a random winner is selected after the round ends.
///      If cancelled or deadline passes without minimum participants, players can claim refunds.
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public minParticipants;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    // Track individual contributions per round for accurate refunds
    mapping(uint256 => mapping(address => uint256)) public roundContributions;
    // Track if a player has already claimed refund for a round
    mapping(uint256 => mapping(address => bool)) public refunded;
    // Track if a round was cancelled (eligible for refunds)
    mapping(uint256 => bool) public roundCancelled;

    event TicketPurchased(address indexed player, uint256 round, uint256 amount);
    event RoundStarted(uint256 indexed round, uint256 endTime, uint256 minParticipants);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round, uint256 participantCount);
    event RefundClaimed(address indexed player, uint256 indexed round, uint256 amount);

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
        roundCancelled[currentRound] = false;
        emit RoundStarted(currentRound, roundEnd, minParticipants);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        roundContributions[currentRound][msg.sender] += msg.value;
        emit TicketPurchased(msg.sender, currentRound, msg.value);
    }

    /// @notice Cancel the current lottery round if deadline passed without enough participants.
    ///         Only callable by owner after round end when below minimum participants.
    function cancelLottery() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length < minParticipants, "Enough participants");
        require(!roundCancelled[currentRound], "Already cancelled");
        
        roundCancelled[currentRound] = true;
        roundEnd = 0;
        emit LotteryCancelled(currentRound, players.length);
    }

    /// @notice Claim refund for a cancelled round. Each participant gets exact contribution back.
    ///         Can only be called once per player per cancelled round.
    function claimRefund(uint256 round) external {
        require(roundCancelled[round], "Round not cancelled");
        require(!refunded[round][msg.sender], "Already refunded");
        
        uint256 contribution = roundContributions[round][msg.sender];
        require(contribution > 0, "No contribution");
        
        refunded[round][msg.sender] = true;
        
        (bool sent, ) = msg.sender.call{value: contribution}("");
        require(sent, "Refund transfer failed");
        
        emit RefundClaimed(msg.sender, round, contribution);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length >= minParticipants, "Below minimum participants");
        require(!roundCancelled[currentRound], "Round cancelled");

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

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }

    /// @notice Check if a player is eligible for refund on a specific round.
    function canClaimRefund(uint256 round, address player) external view returns (bool) {
        return roundCancelled[round] && 
               !refunded[round][player] && 
               roundContributions[round][player] > 0;
    }
}
