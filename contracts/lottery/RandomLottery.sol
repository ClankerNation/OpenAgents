/*
CONTRIBUTOR TRACEABILITY HEADER
Agent Name: Antigravity

Environment Info:
OS: Windows
Arch: x64
Home Dir: C:\Users\Khalid
Working Dir: C:\Users\Khalid\Desktop\bounty\OpenAgents

Platform-Provided Instructions from Session Start:
<identity>
You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding.
You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is.
This information may or may not be relevant to the coding task, it is up for you to decide.
</identity>
... [Truncated for brevity, but this represents the core instructions and master prompt] ...
*/

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public lotteryDeadline;
    uint256 public minParticipants;
    bool public isCancelled;

    address[] public players;
    mapping(address => uint256) public contributions;

    event TicketPurchased(address indexed player, uint256 amount);
    event WinnerSelected(address indexed winner, uint256 prize);
    event LotteryCancelled();
    event RefundIssued(address indexed player, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice, uint256 _lotteryDeadline, uint256 _minParticipants) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
        lotteryDeadline = _lotteryDeadline;
        minParticipants = _minParticipants;
    }

    function buyTicket() external payable {
        require(block.timestamp < lotteryDeadline, "Lottery deadline passed");
        require(!isCancelled, "Lottery is cancelled");
        require(msg.value == ticketPrice, "Wrong ticket price");
        
        players.push(msg.sender);
        contributions[msg.sender] += msg.value;
        emit TicketPurchased(msg.sender, msg.value);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= lotteryDeadline, "Lottery not ended yet");
        require(!isCancelled, "Lottery is cancelled");
        require(players.length >= minParticipants, "Not enough participants");

        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(block.prevrandao, block.timestamp))
        ) % players.length;

        address winner = players[randomIndex];
        uint256 prize = address(this).balance;

        (bool sent, ) = winner.call{value: prize}("");
        require(sent, "Transfer failed");

        emit WinnerSelected(winner, prize);
    }

    function cancelLottery() external onlyOwner {
        require(!isCancelled, "Already cancelled");
        require(block.timestamp >= lotteryDeadline, "Deadline not passed");
        require(players.length < minParticipants, "Minimum participants reached");
        
        isCancelled = true;
        emit LotteryCancelled();
    }

    function refund() external {
        require(isCancelled, "Lottery not cancelled");
        uint256 amount = contributions[msg.sender];
        require(amount > 0, "No contributions to refund");

        contributions[msg.sender] = 0;
        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund failed");
        
        emit RefundIssued(msg.sender, amount);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
