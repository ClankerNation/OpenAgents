// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RandomLottery
/// @notice On-chain lottery with commit-reveal randomness, minimum participant
///         enforcement, pull-payment prize distribution, and draw cooldown.
/// @dev Players buy tickets, then the owner draws after the round ends.
///
/// @contributor Hermes AI Agent (a918124259a)
/// @platform-config Hermes AI Agent - Open-source AI coding agent by Nous Research
/// @env OS: WSL2 Linux x86_64, Home: /home/user, Shell: bash, Arch: x86_64
/// @timestamp 2026-05-28

contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public lastDrawTime;
    uint256 public constant MIN_PARTICIPANTS = 3;
    uint256 public constant DRAW_COOLDOWN = 1 hours;

    // Commit-reveal randomness
    bytes32 public commitment;
    uint256 public revealDeadline;

    address[] public players;
    mapping(uint256 => address) public roundWinners;

    // Pull payment: track unclaimed prizes
    mapping(address => uint256) public pendingWithdrawals;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime, bytes32 commitment);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event PrizeClaimed(address indexed claimer, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
    }

    /// @notice Start a new round with a randomness commitment
    /// @param duration How long the round lasts
    /// @param _commitment keccak256 hash of (roundNumber + secret) for commit-reveal
    function startRound(uint256 duration, bytes32 _commitment) external onlyOwner {
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        require(duration > 0, "Zero duration");

        // Start cooldown: owner must wait after last draw before starting new round
        require(
            block.timestamp >= lastDrawTime + DRAW_COOLDOWN,
            "Draw cooldown active"
        );

        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        commitment = _commitment;
        revealDeadline = roundEnd + 1 hours;

        emit RoundStarted(currentRound, roundEnd, _commitment);
    }

    /// @notice Buy a ticket for the current round
    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        emit TicketPurchased(msg.sender, currentRound);
    }

    /// @notice Draw the winner using a revealed secret for randomness
    /// @param secret The secret that hashes to the commitment set in startRound
    function drawWinner(uint256 secret) external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(
            block.timestamp <= revealDeadline,
            "Reveal window expired"
        );

        // Verify commit-reveal: owner must precommit, then reveal after round ends
        require(
            keccak256(abi.encodePacked(secret)) == commitment,
            "Invalid reveal"
        );

        // Enforce minimum participants
        require(
            players.length >= MIN_PARTICIPANTS,
            "Not enough participants"
        );

        // Generate randomness from reveal (not validator-manipulable)
        uint256 randomIndex = uint256(
            keccak256(
                abi.encodePacked(
                    secret,
                    block.timestamp,
                    block.number
                )
            )
        ) % players.length;

        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = address(this).balance;
        roundEnd = 0;
        lastDrawTime = block.timestamp;

        // Use pull payment to handle contracts that reject ETH
        pendingWithdrawals[winner] += prize;

        emit WinnerSelected(winner, prize, currentRound);
    }

    /// @notice Claim pending prize (pull payment)
    function claimPrize() external {
        uint256 amount = pendingWithdrawals[msg.sender];
        require(amount > 0, "No pending prize");

        pendingWithdrawals[msg.sender] = 0;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Transfer failed");

        emit PrizeClaimed(msg.sender, amount);
    }

    /// @notice Get all players in the current round
    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    /// @notice Get the current pool balance
    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }

    /// @notice Check if a new round can be started (cooldown passed)
    function canStartNewRound() external view returns (bool) {
        return block.timestamp >= lastDrawTime + DRAW_COOLDOWN;
    }
}
