// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor-info rafaio1
 * @timestamp 2026-08-20T00:00:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness with refund mechanism
/// @dev Players buy tickets, and a random winner is selected after the round ends.
///      If cancelled or deadline passes without min participants, refunds are enabled.
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public minParticipants;
    bool public cancelled;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(address => uint256) public contributions; // Track per-player contributions for refunds
    mapping(address => bool) public refunded;

    event TicketPurchased(address indexed player, uint256 round, uint256 amount);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round, uint256 reason);
    event RefundClaimed(address indexed player, uint256 amount, uint256 round);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice, uint256 _minParticipants) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
        minParticipants = _minParticipants;
    }

    function startRound(uint256 duration) external onlyOwner {
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        require(!cancelled, "Contract cancelled");
        
        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        cancelled = false;
        
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(!cancelled, "Lottery cancelled");
        require(msg.value == ticketPrice, "Wrong ticket price");
        
        players.push(msg.sender);
        contributions[msg.sender] += msg.value;
        
        emit TicketPurchased(msg.sender, currentRound, msg.value);
    }

    /// @notice Cancel the lottery if deadline passed without enough participants
    /// @dev Only owner can cancel, and only if round has ended or min participants not met
    function cancelLottery() external onlyOwner {
        require(!cancelled, "Already cancelled");
        require(roundEnd > 0, "No active round");
        require(
            block.timestamp >= roundEnd || players.length < minParticipants,
            "Cannot cancel active valid round"
        );
        
        cancelled = true;
        emit LotteryCancelled(currentRound, players.length < minParticipants ? 1 : 2);
    }

    /// @notice Claim refund after lottery cancellation
    /// @dev Each participant can claim their exact contribution once
    function refund() external {
        require(cancelled, "Lottery not cancelled");
        require(contributions[msg.sender] > 0, "No contribution");
        require(!refunded[msg.sender], "Already refunded");
        
        uint256 amount = contributions[msg.sender];
        refunded[msg.sender] = true;
        contributions[msg.sender] = 0;
        
        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund transfer failed");
        
        emit RefundClaimed(msg.sender, amount, currentRound);
    }

    function drawWinner() external onlyOwner {
        require(!cancelled, "Lottery cancelled");
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length >= minParticipants, "Insufficient participants");

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

    function setMinParticipants(uint256 _min) external onlyOwner {
        minParticipants = _min;
    }
}
