// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends
contract RandomLottery is ReentrancyGuard {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public lastDrawTime;
    uint256 public constant MIN_PARTICIPANTS = 3;
    uint256 public constant DRAW_COOLDOWN = 1 hours;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    
    // Commit-reveal randomness
    bytes32 public randomnessCommit;
    bool public randomnessRevealed;
    uint256 public revealDeadline;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event RandomnessCommitted(bytes32 commit, uint256 revealDeadline);
    event RandomnessRevealed(bytes32 revealedValue);
    event FundsRecovered(address indexed to, uint256 amount);

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
        randomnessCommit = bytes32(0);
        randomnessRevealed = false;
        emit RoundStarted(currentRound, roundEnd);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");
        players.push(msg.sender);
        emit TicketPurchased(msg.sender, currentRound);
    }

    /// @notice Commit randomness seed for the current round. Must be called after round ends.
    /// @param seed The secret seed value (keep private until reveal).
    function commitRandomness(bytes32 seed) external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length >= MIN_PARTICIPANTS, "Insufficient participants");
        require(randomnessCommit == bytes32(0), "Already committed");
        require(block.timestamp >= lastDrawTime + DRAW_COOLDOWN, "Cooldown active");
        
        randomnessCommit = keccak256(abi.encodePacked(seed, block.number));
        revealDeadline = block.timestamp + 1 hours;
        randomnessRevealed = false;
        
        emit RandomnessCommitted(randomnessCommit, revealDeadline);
    }

    /// @notice Reveal the randomness seed and select winner.
    /// @param seed The original seed used in commitRandomness.
    function revealAndDraw(bytes32 seed) external onlyOwner nonReentrant {
        require(randomnessCommit != bytes32(0), "No commit");
        require(!randomnessRevealed, "Already revealed");
        require(block.timestamp <= revealDeadline, "Reveal deadline passed");
        require(keccak256(abi.encodePacked(seed, block.number - 1)) == randomnessCommit || 
                keccak256(abi.encodePacked(seed, block.number)) == randomnessCommit, "Invalid seed");
        
        randomnessRevealed = true;
        uint256 randomValue = uint256(keccak256(abi.encodePacked(seed, block.timestamp)));
        uint256 randomIndex = randomValue % players.length;
        
        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;
        
        uint256 prize = address(this).balance;
        roundEnd = 0;
        lastDrawTime = block.timestamp;
        randomnessCommit = bytes32(0);
        
        // Handle ETH-rejecting winners gracefully
        (bool sent, ) = winner.call{value: prize}("");
        if (!sent) {
            // If winner rejects ETH, hold funds for manual recovery or burn
            emit FundsRecovered(winner, prize);
        }
        
        emit RandomnessRevealed(bytes32(randomValue));
        emit WinnerSelected(winner, prize, currentRound);
    }

    /// @notice Emergency: recover funds if winner rejected ETH and reveal deadline passed.
    function recoverStuckFunds(address to) external onlyOwner {
        require(randomnessRevealed && block.timestamp > revealDeadline, "Not eligible");
        uint256 balance = address(this).balance;
        require(balance > 0, "No funds");
        (bool sent, ) = to.call{value: balance}("");
        require(sent, "Recovery failed");
        emit FundsRecovered(to, balance);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
