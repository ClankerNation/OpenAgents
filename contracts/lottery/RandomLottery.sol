// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
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
    mapping(uint256 => mapping(address => bool)) public refunded;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round, uint256 playerCount);
    event RefundClaimed(address indexed player, uint256 amount, uint256 round);

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
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        emit TicketPurchased(msg.sender, currentRound);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length >= minParticipants, "Insufficient participants - cancel instead");

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

    /// @notice Cancel the current round if deadline passed without enough participants.
    /// @dev Only callable by owner after roundEnd when player count is below minimum.
    function cancelLottery() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round still active");
        require(players.length < minParticipants, "Enough participants");
        require(roundEnd > 0, "No active round");

        emit LotteryCancelled(currentRound, players.length);
        roundEnd = 0; // Mark round as settled (cancelled)
    }

    /// @notice Claim refund for a cancelled round.
    /// @dev Players can claim their ticket price back after cancellation.
    function claimRefund() external {
        require(roundEnd == 0, "Round not cancelled");
        require(!refunded[currentRound][msg.sender], "Already refunded");
        
        // Verify player participated in this round
        bool isPlayer = false;
        for (uint256 i = 0; i < players.length; i++) {
            if (players[i] == msg.sender) {
                isPlayer = true;
                break;
            }
        }
        require(isPlayer, "Not a participant");

        refunded[currentRound][msg.sender] = true;
        (bool sent, ) = msg.sender.call{value: ticketPrice}("");
        require(sent, "Refund failed");

        emit RefundClaimed(msg.sender, ticketPrice, currentRound);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
