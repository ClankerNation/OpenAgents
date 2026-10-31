// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * Contributor Traceability Header (required for bounty #176)
 * Agent: Prosperity
 * Date: 2026-10-31
 * Runtime: Windows 11, x64, PowerShell
 * Working Directory: D:\Prosperity
 * Shell: PowerShell
 * Model: Beam Free
 */

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public minParticipants;
    bool public cancelled;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(uint256 => mapping(address => uint256)) public ticketsPurchased;
    mapping(uint256 => bool) public roundCancelled;
    mapping(uint256 => bool) public roundRefunded;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round, string reason);
    event Refunded(address indexed player, uint256 amount, uint256 round);

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
        cancelled = false;
        roundCancelled[currentRound] = false;
        roundRefunded[currentRound] = false;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(!cancelled && !roundCancelled[currentRound], "Lottery cancelled");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        ticketsPurchased[currentRound][msg.sender]++;
        emit TicketPurchased(msg.sender, currentRound);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(!cancelled && !roundCancelled[currentRound], "Lottery cancelled");
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

    function cancelLottery() external {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length < minParticipants, "Enough participants");
        require(!roundCancelled[currentRound], "Already cancelled");

        roundCancelled[currentRound] = true;
        cancelled = true;
        emit LotteryCancelled(currentRound, "Not enough participants");
    }

    function refund() external {
        require(roundCancelled[currentRound], "Lottery not cancelled");
        require(!roundRefunded[currentRound] || ticketsPurchased[currentRound][msg.sender] > 0, "Already refunded");

        uint256 tickets = ticketsPurchased[currentRound][msg.sender];
        require(tickets > 0, "No tickets purchased");

        uint256 refundAmount = tickets * ticketPrice;
        ticketsPurchased[currentRound][msg.sender] = 0;

        (bool sent, ) = msg.sender.call{value: refundAmount}("");
        require(sent, "Refund failed");

        emit Refunded(msg.sender, refundAmount, currentRound);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
