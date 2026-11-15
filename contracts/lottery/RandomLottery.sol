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
    uint256 public minParticipants;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    /// @notice ETH actually contributed per round per player (exact ticket payments).
    mapping(uint256 => mapping(address => uint256)) public contributions;
    /// @notice True once a round has been cancelled by the owner (refunds open).
    mapping(uint256 => bool) public roundCancelled;
    /// @notice True once a round has had a winner drawn (refunds closed).
    mapping(uint256 => bool) public roundCompleted;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round, uint256 participants, uint256 minParticipants);
    event Refunded(uint256 indexed round, address indexed player, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
    }

    /// @notice Start a new round. `roundEnd` is the lottery deadline: once it
    /// passes without enough participants, the owner may cancel the round.
    /// @param duration Seconds until the round deadline.
    /// @param _minParticipants Minimum players required for the round to be drawable.
    function startRound(uint256 duration, uint256 _minParticipants) external onlyOwner {
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        require(_minParticipants > 0, "Min participants must be > 0");
        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        minParticipants = _minParticipants;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        contributions[currentRound][msg.sender] += msg.value;
        emit TicketPurchased(msg.sender, currentRound);
    }

    /// @notice Cancel the active round once its deadline has passed without
    /// enough participants. Participants can then claim exact refunds via `refund`.
    function cancelLottery() external onlyOwner {
        require(roundEnd != 0, "No active round");
        require(block.timestamp >= roundEnd, "Deadline not passed");
        require(players.length < minParticipants, "Enough participants");
        require(!roundCancelled[currentRound], "Already cancelled");
        require(!roundCompleted[currentRound], "Round completed");

        roundCancelled[currentRound] = true;
        roundEnd = 0;
        emit LotteryCancelled(currentRound, players.length, minParticipants);
    }

    /// @notice Refund the caller's exact contribution for a cancelled round.
    /// Callable any time after cancellation, even after later rounds started.
    function refund(uint256 round) external {
        require(roundCancelled[round], "Lottery not cancelled");
        uint256 amount = contributions[round][msg.sender];
        require(amount > 0, "Nothing to refund");

        contributions[round][msg.sender] = 0;
        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund transfer failed");

        emit Refunded(round, msg.sender, amount);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(!roundCancelled[currentRound], "Lottery cancelled");
        require(players.length >= minParticipants, "Not enough participants");

        // BUG: prevrandao is manipulable by validators — validators can influence
        // the randomness value, making the lottery outcome predictable/riggable
        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(block.prevrandao, block.timestamp))
        ) % players.length;

        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;
        roundCompleted[currentRound] = true;

        uint256 prize = address(this).balance;
        roundEnd = 0;

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
