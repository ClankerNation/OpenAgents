// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
// @fix-author rafaio1
// @date 2026-08-25T04:00:00Z
// @runtime linux x64 /tmp/openagents_issue_202 bash
// @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement, senior dev multi-agent orchestration, and Wise payout integration.

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends
/// @title RandomLottery
/// @notice On-chain lottery with cancellation and per-participant refund support
/// @dev Players buy tickets tracked individually for accurate refunds on cancellation
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public minParticipants;

    address[] public players;
    mapping(uint256 => mapping(address => uint256)) public contributions; // round -> player -> amount
    mapping(uint256 => address) public roundWinners;
    mapping(uint256 => bool) public roundCancelled;
    mapping(uint256 => mapping(address => bool)) public refunded;

    event TicketPurchased(address indexed player, uint256 round, uint256 amount);
    event RoundStarted(uint256 indexed round, uint256 endTime, uint256 minParticipants);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round, uint256 participantCount);
    event Refunded(address indexed player, uint256 indexed round, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice, uint256 _minParticipants) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
        minParticipants = _minParticipants > 0 ? _minParticipants : 2;
    }

    function startRound(uint256 duration) external onlyOwner {
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        roundCancelled[currentRound] = false;
        emit RoundStarted(currentRound, roundEnd, minParticipants);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        require(!roundCancelled[currentRound], "Round cancelled");

        players.push(msg.sender);
        contributions[currentRound][msg.sender] += msg.value;
        emit TicketPurchased(msg.sender, currentRound, msg.value);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(!roundCancelled[currentRound], "Round cancelled");
        require(players.length >= minParticipants, "Below min participants");

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

    /// @notice Cancel lottery if deadline passed without enough participants.
    ///         Enables per-participant refunds via refund().
    function cancelLottery(uint256 _round) external onlyOwner {
        require(_round == currentRound, "Not current round");
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length < minParticipants, "Enough participants — use drawWinner");
        require(!roundCancelled[_round], "Already cancelled");

        roundCancelled[_round] = true;
        roundEnd = 0;
        emit LotteryCancelled(_round, players.length);
    }

    /// @notice Claim refund after lottery cancellation. Each participant gets exact contribution back.
    function refund(uint256 _round) external {
        require(roundCancelled[_round], "Lottery not cancelled");
        require(!refunded[_round][msg.sender], "Already refunded");

        uint256 amount = contributions[_round][msg.sender];
        require(amount > 0, "No contribution to refund");

        refunded[_round][msg.sender] = true;
        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund transfer failed");

        emit Refunded(msg.sender, _round, amount);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }

    function isCancelled(uint256 _round) external view returns (bool) {
        return roundCancelled[_round];
    }

    function getContribution(uint256 _round, address player) external view returns (uint256) {
        return contributions[_round][player];
    }
}
