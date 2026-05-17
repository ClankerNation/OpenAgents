// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Contributor: Gaotax2006
// Platform: warpSpeed bounty agent, opencode CLI
// Runtime: OS=win32 Arch=x64 Home=C:\Users\asus WorkDir=F:\ai-bounty-work\bounty-hunter\openagents Shell=powershell
// Date: 2026-05-17

contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public lastDrawTime;
    uint256 public constant MIN_PARTICIPANTS = 3;
    uint256 public constant DRAW_COOLDOWN = 1 hours;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(address => uint256) public pendingWithdrawals;
    mapping(address => bytes32) public commitments;
    mapping(address => bool) public hasRevealed;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event Withdrawal(address indexed winner, uint256 amount);
    event Committed(address indexed player, bytes32 commitment);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
    }

    function startRound(uint256 duration) external onlyOwner {
        require(block.timestamp >= lastDrawTime + DRAW_COOLDOWN, "Cooldown active");
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

    function commit(bytes32 secretHash) external {
        require(block.timestamp < roundEnd, "Round ended");
        bool isPlayer = false;
        for (uint256 i = 0; i < players.length; i++) {
            if (players[i] == msg.sender) {
                isPlayer = true;
                break;
            }
        }
        require(isPlayer, "Not a player");
        require(commitments[msg.sender] == bytes32(0), "Already committed");
        commitments[msg.sender] = secretHash;
        emit Committed(msg.sender, secretHash);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length >= MIN_PARTICIPANTS, "Not enough participants");
        require(roundWinners[currentRound] == address(0), "Already drawn");

        uint256 seed = uint256(keccak256(abi.encodePacked(blockhash(block.number - 1), block.timestamp)));

        for (uint256 i = 0; i < players.length; i++) {
            if (commitments[players[i]] != bytes32(0)) {
                seed ^= uint256(commitments[players[i]]);
            }
        }

        uint256 randomIndex = seed % players.length;
        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = address(this).balance;
        roundEnd = 0;
        lastDrawTime = block.timestamp;

        (bool sent, ) = winner.call{value: prize}("");
        if (!sent) {
            pendingWithdrawals[winner] += prize;
        }

        emit WinnerSelected(winner, prize, currentRound);
    }

    function withdraw() external {
        uint256 amount = pendingWithdrawals[msg.sender];
        require(amount > 0, "Nothing to withdraw");
        pendingWithdrawals[msg.sender] = 0;
        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Transfer failed");
        emit Withdrawal(msg.sender, amount);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
