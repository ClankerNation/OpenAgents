// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public lotteryDeadline;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(address => bool) public refunded;
    mapping(uint256 => uint256) public roundTicketCount;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round);
    event Refunded(address indexed player, uint256 amount, uint256 round);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
    }

    function startRound(uint256 duration, uint256 _deadline) external onlyOwner {
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        require(_deadline > duration, "Deadline must be after round end");
        delete players;
        delete refunded;
        currentRound++;
        roundEnd = block.timestamp + duration;
        lotteryDeadline = block.timestamp + _deadline;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        roundTicketCount[currentRound]++;
        emit TicketPurchased(msg.sender, currentRound);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(roundTicketCount[currentRound] >= 2, "Need at least 2 participants");

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
        require(block.timestamp >= lotteryDeadline, "Deadline not reached");
        require(roundEnd == 0 || block.timestamp < roundEnd, "Round already ended");
        require(roundTicketCount[currentRound] < 2, "Enough participants — draw instead");

        emit LotteryCancelled(currentRound);
        roundEnd = 0;
    }

    function refund() external {
        require(block.timestamp >= lotteryDeadline, "Deadline not reached");
        require(!refunded[msg.sender], "Already refunded");

        bool wasParticipant;
        for (uint256 i = 0; i < players.length; i++) {
            if (players[i] == msg.sender) {
                wasParticipant = true;
                break;
            }
        }
        require(wasParticipant, "Not a participant");

        refunded[msg.sender] = true;
        uint256 refundAmount = ticketPrice;

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
