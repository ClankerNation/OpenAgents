// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends
/// @custom:generated-by Codex
/// @custom:runtime os=Darwin arch=arm64 home_dir=/Users/nicdunz working_dir=/Users/nicdunz/Documents/money making/runs/2026-05-20-openagents-agenttoken-permit-158/OpenAgents shell=zsh
/// @custom:date 2026-05-20T10:15:13Z
/// @custom:note Private platform/session initialization text omitted from public source artifact.
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public constant DEFAULT_MIN_PARTICIPANTS = 2;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(uint256 => bool) public roundCancelled;
    mapping(uint256 => bool) public roundCompleted;
    mapping(uint256 => uint256) public roundPool;
    mapping(uint256 => uint256) public roundMinParticipants;
    mapping(uint256 => mapping(address => uint256)) public contributions;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round);
    event RefundIssued(address indexed player, uint256 indexed round, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
    }

    function startRound(uint256 duration) external onlyOwner {
        _startRound(duration, DEFAULT_MIN_PARTICIPANTS);
    }

    function startRound(uint256 duration, uint256 minParticipants) external onlyOwner {
        _startRound(duration, minParticipants);
    }

    function _startRound(uint256 duration, uint256 minParticipants) internal {
        require(duration > 0, "Invalid duration");
        require(minParticipants > 1, "Invalid min participants");
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        roundMinParticipants[currentRound] = minParticipants;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(!roundCancelled[currentRound], "Round cancelled");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        contributions[currentRound][msg.sender] += msg.value;
        roundPool[currentRound] += msg.value;
        emit TicketPurchased(msg.sender, currentRound);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(!roundCancelled[currentRound], "Round cancelled");
        require(!roundCompleted[currentRound], "Round completed");
        require(players.length >= roundMinParticipants[currentRound], "Not enough participants");

        // BUG: prevrandao is manipulable by validators — validators can influence
        // the randomness value, making the lottery outcome predictable/riggable
        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(block.prevrandao, block.timestamp))
        ) % players.length;

        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = roundPool[currentRound];
        roundPool[currentRound] = 0;
        roundCompleted[currentRound] = true;
        roundEnd = 0;

        // BUG: Winner can be a contract that rejects ETH (no receive/fallback),
        // causing this call to revert and locking all funds permanently
        (bool sent, ) = winner.call{value: prize}("");
        require(sent, "Transfer failed");

        emit WinnerSelected(winner, prize, currentRound);
    }

    function cancelLottery() external {
        require(roundEnd != 0, "No active round");
        require(block.timestamp >= roundEnd, "Round not ended");
        require(!roundCompleted[currentRound], "Round completed");
        require(players.length < roundMinParticipants[currentRound], "Enough participants");
        roundCancelled[currentRound] = true;
        roundEnd = 0;
        emit LotteryCancelled(currentRound);
    }

    function refund(uint256 round) external {
        require(roundCancelled[round], "Lottery not cancelled");
        require(!roundCompleted[round], "Round completed");
        uint256 amount = contributions[round][msg.sender];
        require(amount > 0, "Nothing to refund");
        contributions[round][msg.sender] = 0;
        roundPool[round] -= amount;
        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund failed");
        emit RefundIssued(msg.sender, round, amount);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }

    function getRoundPoolSize(uint256 round) external view returns (uint256) {
        return roundPool[round];
    }
}
