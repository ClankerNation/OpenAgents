// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends
/// @author Gaotax2006
/// @traceability contributor: Gaotax2006 — fix #176: added lotteryDeadline, cancelLottery, refund, contribution tracking
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public lotteryDeadline;
    uint256 public currentRound;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(address => uint256) public contributions;

    bool public lotteryActive;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round);
    event Refunded(address indexed player, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
    }

    function startRound(uint256 duration) external onlyOwner {
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        delete players;
        delete contributions;
        currentRound++;
        roundEnd = block.timestamp + duration;
        lotteryDeadline = block.timestamp + duration + 1 days;
        lotteryActive = true;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        contributions[msg.sender] += msg.value;
        emit TicketPurchased(msg.sender, currentRound);
    }

    function cancelLottery() external onlyOwner {
        require(lotteryActive, "Lottery not active");
        require(block.timestamp >= roundEnd, "Round not ended");
        require(block.timestamp <= lotteryDeadline, "Deadline passed");
        lotteryActive = false;
        emit LotteryCancelled(currentRound);
    }

    function refund() external {
        require(!lotteryActive, "Lottery still active");
        require(contributions[msg.sender] > 0, "No contribution");

        uint256 amount = contributions[msg.sender];
        contributions[msg.sender] = 0;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund failed");

        emit Refunded(msg.sender, amount);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");

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
        lotteryActive = false;

        // BUG: Winner can be a contract that rejects ETH (no receive/fallback),
        // causing this call to revert and locking all funds permanently
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
}
