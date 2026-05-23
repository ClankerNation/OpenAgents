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

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(address => uint256) public contributions;
    uint256 public minParticipants;
    uint256 public lotteryDeadline;
    bool public cancelled;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 round);
    event Refunded(address indexed player, uint256 amount, uint256 round);

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
        cancelled = false;
        currentRound++;
        roundEnd = block.timestamp + duration;
        lotteryDeadline = block.timestamp + duration + 7 days;
        minParticipants = _minParticipants;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        require(!cancelled, "Round cancelled");
        players.push(msg.sender);
        contributions[msg.sender] += msg.value;
        emit TicketPurchased(msg.sender, currentRound);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(!cancelled, "Round cancelled");

        // BUG: prevrandao is manipulable by validators — validators can influence
        // the randomness value, making the lottery outcome predictable/riggable
        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(block.prevrandao, block.timestamp))
        ) % players.length;

        // BUG: No minimum participants check — if only 1 player entered,
        // the lottery is pointless and the single player always wins their own funds minus gas
        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = address(this).balance;
        roundEnd = 0;

        // BUG: Winner can be a contract that rejects ETH (no receive/fallback),
        // causing this call to revert and locking all funds permanently
        (bool sent, ) = winner.call{value: prize}("");
        require(sent, "Transfer failed");

        emit WinnerSelected(winner, prize, currentRound);
    }

    function cancelLottery() external onlyOwner {
        require(block.timestamp >= lotteryDeadline, "Deadline not passed");
        require(players.length < minParticipants, "Enough participants");
        require(!cancelled, "Already cancelled");
        cancelled = true;
        roundEnd = 0;
        emit LotteryCancelled(currentRound);
    }

    function refund() external {
        require(cancelled, "Not cancelled");
        uint256 amount = contributions[msg.sender];
        require(amount > 0, "Nothing to refund");
        contributions[msg.sender] = 0;
        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund failed");
        emit Refunded(msg.sender, amount, currentRound);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
