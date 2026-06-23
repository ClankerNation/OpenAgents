// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends.
///      Includes minimum participant check, refund on cancellation, and pull-pattern withdrawal.
/// @contributor Gaotax2006
/// @platform claude-code/opus-4.8
/// @runtime node-v24.15.0 / win32 / amd64
/// @date 2026-06-24
/// @fixes #176 — Added lotteryDeadline, cancelLottery, refund, minParticipants, pull-withdraw

contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public lotteryDeadline; // deadline for the entire lottery lifecycle
    uint256 public minParticipants;  // minimum players required to draw a winner

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(address => uint256) public pendingRefunds; // pull-pattern refunds

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
        lotteryDeadline = block.timestamp + duration + 1 hours; // 1 hour grace after round end
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
     *         All participants can then claim refunds.
     */
    function cancelLottery() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round still active");
        require(block.timestamp <= lotteryDeadline, "Lottery deadline passed");
        require(players.length < minParticipants, "Min participants met");

        uint256 participantCount = players.length;

        // Calculate per-person refund
        uint256 refundPerPerson = address(this).balance / participantCount;
        for (uint256 i = 0; i < participantCount; i++) {
            pendingRefunds[players[i]] += refundPerPerson;
        }

        // Clear player list
        delete players;
        roundEnd = 0;

        emit LotteryCancelled(currentRound, participantCount);
    }

    /**
     * @notice Claim a refund after lottery cancellation (pull pattern).
     */
    function refund() external {
        uint256 amount = pendingRefunds[msg.sender];
        require(amount > 0, "No refund available");
        pendingRefunds[msg.sender] = 0;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund transfer failed");

        emit RefundProcessed(msg.sender, amount);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length >= minParticipants, "Not enough participants");

        // Use block.prevrandao with additional entropy sources
        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(block.prevrandao, block.timestamp, currentRound, players.length))
        ) % players.length;

        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = address(this).balance;
        roundEnd = 0;

        // Pull pattern — winner must call withdraw() to prevent contract rejection
        pendingRefunds[winner] += prize;

        emit WinnerSelected(winner, prize, currentRound);
    }

    /**
     * @notice Withdraw accumulated refund (for winner or cancelled-lottery participant).
     */
    function withdraw() external {
        uint256 amount = pendingRefunds[msg.sender];
        require(amount > 0, "No funds to withdraw");
        pendingRefunds[msg.sender] = 0;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Withdrawal failed");
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
