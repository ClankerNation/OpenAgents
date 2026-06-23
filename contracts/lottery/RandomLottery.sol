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

    bool public roundCancelled;
    mapping(address => bool) public refunded;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event RoundCancelled(uint256 indexed round);
    event Refunded(address indexed player, uint256 amount);
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
        delete players;
        delete roundWinners;
        delete refunded;
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
        emit TicketPurchased(msg.sender, currentRound);
    }

    function cancelRound() external onlyOwner {
        require(roundEnd != 0, "No active round");
        require(block.timestamp < roundEnd, "Round already ended");
        require(!roundCancelled, "Already cancelled");

        roundCancelled = true;
        emit RoundCancelled(currentRound);
    }

    function refundPlayer(address player) external onlyOwner {
        require(roundCancelled, "Round not cancelled");
        require(!refunded[player], "Already refunded");

        uint256 balance = address(this).balance;
        require(balance >= ticketPrice, "Insufficient funds");

        refunded[player] = true;

        // Remove player from array to keep indices valid
        for (uint256 i = 0; i < players.length; i++) {
            if (players[i] == player) {
                players[i] = players[players.length - 1];
                players.pop();
                break;
            }
        }

        (bool sent, ) = player.call{value: ticketPrice}("");
        require(sent, "Refund failed");

        emit Refunded(player, ticketPrice);
    }

    function refundAll() external onlyOwner {
        require(roundCancelled, "Round not cancelled");

        uint256 playerCount = players.length;
        uint256 balance = address(this).balance;
        require(balance >= playerCount * ticketPrice, "Insufficient funds");

        for (uint256 i = 0; i < playerCount; i++) {
            address player = players[i];
            refunded[player] = true;

            (bool sent, ) = player.call{value: ticketPrice}("");
            require(sent, "Refund failed");
        }

        delete players;
    }

    function drawWinner() external onlyOwner {
        require(!roundCancelled, "Round cancelled");
        require(block.timestamp >= roundEnd, "Round not ended");

        require(players.length > 0, "No players");

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

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
