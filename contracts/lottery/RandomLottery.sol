// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author rafaio1
// @date 2026-08-20
// @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
// @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

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
    mapping(uint256 => mapping(address => uint256)) public contributions;
    mapping(uint256 => bool) public roundCancelled;
    mapping(uint256 => mapping(address => bool)) public refunded;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event RoundCancelled(uint256 indexed round, uint256 reason);
    event Refunded(address indexed player, uint256 amount, uint256 round);

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
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(!roundCancelled[currentRound], "Round cancelled");
        require(msg.value == ticketPrice, "Wrong ticket price");
        
        contributions[currentRound][msg.sender] += msg.value;
        players.push(msg.sender);
        emit TicketPurchased(msg.sender, currentRound);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(!roundCancelled[currentRound], "Round cancelled");
        require(players.length >= minParticipants, "Not enough participants");

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

    /// @notice Cancel the current round if deadline passed without enough participants
    function cancelLottery() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(!roundCancelled[currentRound], "Already cancelled");
        require(players.length < minParticipants, "Enough participants");
        
        roundCancelled[currentRound] = true;
        roundEnd = 0;
        emit RoundCancelled(currentRound, 1); // 1 = insufficient participants
    }

    /// @notice Claim refund after round cancellation
    function claimRefund(uint256 _roundId) external {
        require(roundCancelled[_roundId], "Round not cancelled");
        require(!refunded[_roundId][msg.sender], "Already refunded");
        
        uint256 amount = contributions[_roundId][msg.sender];
        require(amount > 0, "No contribution");
        
        refunded[_roundId][msg.sender] = true;
        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund failed");
        
        emit Refunded(msg.sender, amount, _roundId);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }

    function getPlayerContribution(uint256 _roundId, address player) external view returns (uint256) {
        return contributions[_roundId][player];
    }
}
