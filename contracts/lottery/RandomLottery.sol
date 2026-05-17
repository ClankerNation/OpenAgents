// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Contributor: Gaotax2006
// Platform: warpSpeed, opencode CLI
// Runtime: OS=win32 Arch=x64 Home=C:\Users\asus WorkDir=F:\ai-bounty-work\bounty-hunter\openagents Shell=powershell
// Date: 2026-05-17

contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public constant MIN_PARTICIPANTS = 2;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(address => uint256) public contributions;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round);
    event RefundIssued(address indexed player, uint256 amount, uint256 indexed round);

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
        currentRound++;
        roundEnd = block.timestamp + duration;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        contributions[msg.sender] += msg.value;
        emit TicketPurchased(msg.sender, currentRound);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length >= MIN_PARTICIPANTS, "Not enough participants");

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

    function cancelLottery() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length < MIN_PARTICIPANTS, "Has enough participants");
        roundEnd = 0;
        emit LotteryCancelled(currentRound);
    }

    function refund() external {
        require(roundEnd == 0 && players.length < MIN_PARTICIPANTS, "Not cancellable");
        uint256 amount = contributions[msg.sender];
        require(amount > 0, "Nothing to refund");
        contributions[msg.sender] = 0;
        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund failed");
        emit RefundIssued(msg.sender, amount, currentRound);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
