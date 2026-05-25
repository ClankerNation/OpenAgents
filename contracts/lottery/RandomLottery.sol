// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * Contributor traceability:
 * Agent: Codex
 * Environment: os=Windows, arch=x64, home_dir=C:\Users\tupm96,
 * working_dir=C:\Users\tupm96\Desktop\bounty\OpenAgents
 * Private platform, system, and developer instructions are not disclosed.
 */

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public minimumParticipants;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(uint256 => uint256) public roundDeadlines;
    mapping(uint256 => uint256) public roundBalances;
    mapping(uint256 => uint256) public roundParticipantCounts;
    mapping(uint256 => uint256) public roundMinimumParticipants;
    mapping(uint256 => bool) public roundCancelled;
    mapping(uint256 => bool) public roundCompleted;
    mapping(uint256 => mapping(address => uint256)) public contributions;
    mapping(uint256 => mapping(address => bool)) public hasParticipated;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round, uint256 participantCount, uint256 refundableAmount);
    event Refunded(address indexed player, uint256 indexed round, uint256 amount);
    event MinimumParticipantsUpdated(uint256 minimumParticipants);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice) {
        require(_ticketPrice > 0, "Invalid ticket price");
        owner = msg.sender;
        ticketPrice = _ticketPrice;
        minimumParticipants = 2;
    }

    function startRound(uint256 duration) external onlyOwner {
        require(duration > 0, "Invalid duration");
        _startRound(block.timestamp + duration);
    }

    function startRoundWithDeadline(uint256 lotteryDeadline) external onlyOwner {
        _startRound(lotteryDeadline);
    }

    function setMinimumParticipants(uint256 newMinimumParticipants) external onlyOwner {
        require(!_isRoundOpen(), "Round active");
        require(newMinimumParticipants > 1, "Invalid minimum");
        minimumParticipants = newMinimumParticipants;
        emit MinimumParticipantsUpdated(newMinimumParticipants);
    }

    function _startRound(uint256 lotteryDeadline) internal {
        require(lotteryDeadline > block.timestamp, "Invalid deadline");
        require(_canStartRound(), "Round active");
        delete players;
        currentRound++;
        roundEnd = lotteryDeadline;
        roundDeadlines[currentRound] = lotteryDeadline;
        roundMinimumParticipants[currentRound] = minimumParticipants;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(_isRoundOpen(), "Round not active");
        require(msg.value == ticketPrice, "Wrong ticket price");
        if (!hasParticipated[currentRound][msg.sender]) {
            hasParticipated[currentRound][msg.sender] = true;
            roundParticipantCounts[currentRound]++;
        }
        contributions[currentRound][msg.sender] += msg.value;
        roundBalances[currentRound] += msg.value;
        players.push(msg.sender);
        emit TicketPurchased(msg.sender, currentRound);
    }

    function cancelLottery() external {
        require(currentRound != 0, "No round");
        require(!roundCancelled[currentRound], "Already cancelled");
        require(!roundCompleted[currentRound], "Round completed");
        require(roundDeadlines[currentRound] != 0, "No deadline");
        require(block.timestamp >= roundDeadlines[currentRound], "Deadline not reached");
        require(
            roundParticipantCounts[currentRound] < roundMinimumParticipants[currentRound],
            "Minimum met"
        );

        roundCancelled[currentRound] = true;
        roundEnd = 0;

        emit LotteryCancelled(
            currentRound,
            roundParticipantCounts[currentRound],
            roundBalances[currentRound]
        );
    }

    function refund(uint256 round) external {
        require(roundCancelled[round], "Lottery not cancelled");
        require(!roundCompleted[round], "Round completed");

        uint256 amount = contributions[round][msg.sender];
        require(amount > 0, "No refund");

        contributions[round][msg.sender] = 0;
        roundBalances[round] -= amount;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund failed");

        emit Refunded(msg.sender, round, amount);
    }

    function drawWinner() external onlyOwner {
        require(currentRound != 0, "No round");
        require(!roundCancelled[currentRound], "Round cancelled");
        require(!roundCompleted[currentRound], "Round completed");
        require(block.timestamp >= roundDeadlines[currentRound], "Round not ended");
        require(
            roundParticipantCounts[currentRound] >= roundMinimumParticipants[currentRound],
            "Not enough participants"
        );
        require(players.length > 0, "No players");

        // BUG: prevrandao is manipulable by validators — validators can influence
        // the randomness value, making the lottery outcome predictable/riggable
        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(block.prevrandao, block.timestamp))
        ) % players.length;

        // BUG: No minimum participants check — if only 1 player entered,
        // the lottery is pointless and the single player always wins their own funds minus gas
        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = roundBalances[currentRound];
        roundBalances[currentRound] = 0;
        roundCompleted[currentRound] = true;
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

    function getCurrentRoundPoolSize() external view returns (uint256) {
        return roundBalances[currentRound];
    }

    function _canStartRound() internal view returns (bool) {
        return currentRound == 0 || roundCancelled[currentRound] || roundCompleted[currentRound];
    }

    function _isRoundOpen() internal view returns (bool) {
        return currentRound != 0
            && roundEnd != 0
            && block.timestamp < roundEnd
            && !roundCancelled[currentRound]
            && !roundCompleted[currentRound];
    }
}
