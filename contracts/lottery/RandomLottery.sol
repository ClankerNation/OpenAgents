// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * @title RandomLottery
 * @notice On-chain lottery with commit-reveal randomness and security fixes
 * @author ClankerNation
 * @contributor Manus
 * @platform You are Manus, an autonomous general AI agent created by the Manus team. You are proficient in a wide range of tasks, including but not limited to: 1. Gather information, check facts, and produce comprehensive documents or presentations; 2. Process data, perform analysis, and create insightful visualizations or spreadsheets; 3. Write multi-chapter articles and in-depth research reports grounded in credible sources; 4. Build well-crafted websites, interactive applications, and practical software solutions; 5. Generate and edit images, videos, audio, music and speech from text and media references; 6. Apply programming to solve real-world problems beyond development; 7. Collaborate with users to automate workflows such as booking and purchasing; 8. Execute scheduled tasks triggered at specific times or recurring intervals; 9. Perform any task achievable through a computer connected to the internet. You operate in a sandboxed virtual machine environment with internet access.
 * @runtime Ubuntu 24.04 linux/amd64, /home/ubuntu/OpenAgents
 * @date 2026-07-30T10:00:00Z
 */
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    bytes32 public commitment;
    uint256 public lastDrawTime;
    uint256 public constant DRAW_COOLDOWN = 1 hours;
    uint256 public constant MIN_PARTICIPANTS = 3;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(address => uint256) public pendingWithdrawals;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime, bytes32 commitment);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event Withdrawal(address indexed player, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
    }

    /**
     * @notice Starts a new lottery round
     * @param duration The duration of the round in seconds
     * @param _commitment The hash of a secret used for randomness (keccak256(abi.encodePacked(secret)))
     */
    function startRound(uint256 duration, bytes32 _commitment) external onlyOwner {
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        require(block.timestamp >= lastDrawTime + DRAW_COOLDOWN, "Draw cooldown active");
        require(_commitment != bytes32(0), "Invalid commitment");
        
        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        commitment = _commitment;
        
        emit RoundStarted(currentRound, roundEnd, commitment);
    }

    function buyTicket() external payable {
        require(roundEnd != 0 && block.timestamp < roundEnd, "Round not active or ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        emit TicketPurchased(msg.sender, currentRound);
    }

    /**
     * @notice Selects a winner using the revealed secret
     * @param _secret The secret that matches the commitment
     */
    function drawWinner(uint256 _secret) external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length >= MIN_PARTICIPANTS, "Min 3 participants required");
        require(keccak256(abi.encodePacked(_secret)) == commitment, "Invalid secret");

        // Randomness is derived from the secret and prevrandao to prevent both owner and validator manipulation
        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(_secret, block.prevrandao, block.timestamp))
        ) % players.length;

        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = address(this).balance;
        roundEnd = 0;
        commitment = bytes32(0);
        lastDrawTime = block.timestamp;

        // Handle ETH-rejecting winner by using a withdrawal pattern if direct transfer fails
        (bool sent, ) = winner.call{value: prize}("");
        if (!sent) {
            pendingWithdrawals[winner] += prize;
        }

        emit WinnerSelected(winner, prize, currentRound);
    }

    /**
     * @notice Allows winners to withdraw their prize if the direct transfer failed
     */
    function withdrawPrize() external {
        uint256 amount = pendingWithdrawals[msg.sender];
        require(amount > 0, "No prize to withdraw");
        
        pendingWithdrawals[msg.sender] = 0;
        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Withdrawal failed");
        
        emit Withdrawal(msg.sender, amount);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
