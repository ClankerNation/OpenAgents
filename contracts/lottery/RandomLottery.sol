// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * @contributor Codex
 * @timestamp 2026-05-25T11:43:00Z
 * @env os=Windows, arch=x64, home_dir=C:\Users\tupm96,
 * working_dir=C:\Users\tupm96\Desktop\bounty\OpenAgents, shell=powershell
 * Private platform, system, and developer instructions are not disclosed.
 */

/// @title RandomLottery
/// @notice On-chain lottery using owner commit-reveal randomness.
/// @dev Players buy tickets, and a committed entropy reveal selects the winner after cooldown.
contract RandomLottery {
    uint256 public constant MIN_PARTICIPANTS = 3;
    uint256 public constant DRAW_COOLDOWN = 1 hours;

    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public revealAfter;
    uint256 public currentRound;
    uint256 public roundPool;
    bytes32 public randomCommitment;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(address => uint256) public pendingPrizes;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event RoundCancelled(uint256 indexed round, uint256 refundedTickets);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event PrizeClaimed(address indexed winner, address indexed recipient, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice) {
        require(_ticketPrice > 0, "Invalid ticket price");
        owner = msg.sender;
        ticketPrice = _ticketPrice;
    }

    function startRound(uint256 duration, bytes32 entropyCommitment) external onlyOwner {
        require(roundEnd == 0, "Round active");
        require(duration > 0, "Invalid duration");
        require(entropyCommitment != bytes32(0), "Commitment required");

        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;
        revealAfter = roundEnd + DRAW_COOLDOWN;
        randomCommitment = entropyCommitment;
        roundPool = 0;

        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(roundEnd != 0, "Round inactive");
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");

        players.push(msg.sender);
        roundPool += msg.value;

        emit TicketPurchased(msg.sender, currentRound);
    }

    function drawWinner(bytes32 entropy) external onlyOwner {
        require(roundEnd != 0, "Round inactive");
        require(block.timestamp >= roundEnd, "Round not ended");
        require(block.timestamp >= revealAfter, "Cooldown active");
        require(players.length >= MIN_PARTICIPANTS, "Not enough players");
        require(keccak256(abi.encodePacked(entropy)) == randomCommitment, "Bad reveal");

        uint256 randomIndex = uint256(
            keccak256(abi.encode(entropy, currentRound, address(this), players.length))
        ) % players.length;

        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = roundPool;
        pendingPrizes[winner] += prize;
        roundPool = 0;
        roundEnd = 0;
        revealAfter = 0;
        randomCommitment = bytes32(0);

        emit WinnerSelected(winner, prize, currentRound);
    }

    function cancelRound() external onlyOwner {
        require(roundEnd != 0, "Round inactive");
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length < MIN_PARTICIPANTS, "Enough players");

        uint256 refundedTickets = players.length;
        for (uint256 i = 0; i < refundedTickets; i++) {
            pendingPrizes[players[i]] += ticketPrice;
        }

        roundPool = 0;
        roundEnd = 0;
        revealAfter = 0;
        randomCommitment = bytes32(0);

        emit RoundCancelled(currentRound, refundedTickets);
    }

    function claimPrize() external {
        _claimPrize(payable(msg.sender));
    }

    function claimPrizeTo(address payable recipient) external {
        _claimPrize(recipient);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return roundPool;
    }

    function _claimPrize(address payable recipient) internal {
        require(recipient != address(0), "Invalid recipient");

        uint256 amount = pendingPrizes[msg.sender];
        require(amount > 0, "No prize");

        pendingPrizes[msg.sender] = 0;
        (bool sent, ) = recipient.call{value: amount}("");
        require(sent, "Transfer failed");

        emit PrizeClaimed(msg.sender, recipient, amount);
    }
}
