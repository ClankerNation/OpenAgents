// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
* @fix-author ARO-Agentic | 2026-08-19
* @runtime os=linux arch=x64 working_dir=/tmp/OpenAgents shell=bash
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
    mapping(address => uint256) public ticketCounts;
    mapping(address => bool) public refunded;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round);
    event Refunded(address indexed player, uint256 amount);

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
        
        // Reset refunded status for new round
        // In a production contract we'd need an iterable mapping or event log to clear efficiently
        // For this implementation we rely on checking `cancelled` state per round or simply letting it be.
        // Since `ticketCounts` is per user, we should reset it.
        for (uint i = 0; i < players.length; i++) {
            ticketCounts[players[i]] = 0;
            refunded[players[i]] = false;
        }
        
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        require(!cancelled, "Lottery cancelled");
        
        players.push(msg.sender);
        ticketCounts[msg.sender] += 1;
        emit TicketPurchased(msg.sender, currentRound);
    }

    function cancelLottery() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length < minParticipants, "Enough participants");
        require(!cancelled, "Already cancelled");
        
        cancelled = true;
        emit LotteryCancelled(currentRound);
    }

    function refund() external {
        require(cancelled, "Lottery not cancelled");
        require(!refunded[msg.sender], "Already refunded");
        
        uint256 tickets = ticketCounts[msg.sender];
        require(tickets > 0, "No tickets");
        
        uint256 amount = tickets * ticketPrice;
        refunded[msg.sender] = true;
        ticketCounts[msg.sender] = 0;
        
        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Transfer failed");
        
        emit Refunded(msg.sender, amount);
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

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
    
    receive() external payable {}
}
