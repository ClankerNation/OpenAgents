// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends.
///      Includes cancellation with refund if minimum participants not met.
/// @contributor Gaotax2006
/// @platform claude-code/opus-4.8
/// @runtime node-v24.15.0 / win32 / amd64
/// @date 2026-06-24
/// @fixes #167 — Added lotteryDeadline, cancelLottery, refund for participants

contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public lotteryDeadline; // deadline by which lottery must end or be cancelled
    uint256 public currentRound;
    uint256 public minParticipants;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(address => uint256) public pendingRefunds;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round, uint256 participantCount);
    event RefundProcessed(address indexed player, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
        minParticipants = 3;
    }

    function startRound(uint256 duration) external onlyOwner {
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        lotteryDeadline = block.timestamp + duration + 2 hours;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        emit TicketPurchased(msg.sender, currentRound);
    }

    /**
     * @notice Cancel the lottery if minimum participants not reached by deadline.
     */
    function cancelLottery() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round still active");
        require(block.timestamp <= lotteryDeadline, "Before deadline");
        require(players.length < minParticipants, "Min participants met");

        uint256 count = players.length;
        uint256 refundPerPerson = address(this).balance / count;
        for (uint256 i = 0; i < count; i++) {
            pendingRefunds[players[i]] += refundPerPerson;
        }

        delete players;
        roundEnd = 0;
        emit LotteryCancelled(currentRound, count);
    }

    /**
     * @notice Claim refund after lottery cancellation.
     */
    function refund() external {
        uint256 amount = pendingRefunds[msg.sender];
        require(amount > 0, "No refund available");
        pendingRefunds[msg.sender] = 0;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund failed");

        emit RefundProcessed(msg.sender, amount);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length >= minParticipants, "Not enough participants");

        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(block.prevrandao, block.timestamp, currentRound))
        ) % players.length;

        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = address(this).balance;
        roundEnd = 0;

        // Use pendingRefunds for pull pattern — winner must call withdraw()
        pendingRefunds[winner] += prize;

        emit WinnerSelected(winner, prize, currentRound);
    }

    function withdraw() external {
        uint256 amount = pendingRefunds[msg.sender];
        require(amount > 0, "No funds");
        pendingRefunds[msg.sender] = 0;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Withdraw failed");
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
