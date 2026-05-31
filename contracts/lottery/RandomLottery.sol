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
    uint256 public constant MIN_PARTICIPANTS = 2;
    bool public roundCancelled;
    uint256 public pendingRefundPool;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(uint256 => mapping(address => uint256)) public contributions;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event LotteryCancelled(uint256 indexed round, uint256 refundPool);
    event Refunded(address indexed player, uint256 amount, uint256 indexed round);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);

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
        require(!roundCancelled || pendingRefundPool == 0, "Pending refunds");
        delete players;
        roundCancelled = false;
        currentRound++;
        roundEnd = block.timestamp + duration;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(!roundCancelled, "Round cancelled");
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        contributions[currentRound][msg.sender] += msg.value;
        pendingRefundPool += msg.value;
        emit TicketPurchased(msg.sender, currentRound);
    }

    function drawWinner() external onlyOwner {
        require(!roundCancelled, "Round cancelled");
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length >= MIN_PARTICIPANTS, "Not enough participants");

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
        pendingRefundPool = 0;
        roundEnd = 0;

        // BUG: Winner can be a contract that rejects ETH (no receive/fallback),
        // causing this call to revert and locking all funds permanently
        (bool sent, ) = winner.call{value: prize}("");
        require(sent, "Transfer failed");

        emit WinnerSelected(winner, prize, currentRound);
    }

    function cancelLottery() external {
        require(!roundCancelled, "Already cancelled");
        require(roundEnd != 0, "No active round");
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length < MIN_PARTICIPANTS, "Enough participants");
        roundCancelled = true;
        roundEnd = 0;
        emit LotteryCancelled(currentRound, pendingRefundPool);
    }

    function refund() external {
        require(roundCancelled, "Round not cancelled");
        uint256 amount = contributions[currentRound][msg.sender];
        require(amount > 0, "Nothing to refund");

        contributions[currentRound][msg.sender] = 0;
        pendingRefundPool -= amount;

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
