// @contributor rafaio1
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

    // Commit-reveal randomness
    bytes32 public commitHash;
    uint256 public revealDeadline;
    bool public committed;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round, uint256 playerCount);
    event RefundClaimed(address indexed player, uint256 amount, uint256 round);
    event RandomnessCommitted(bytes32 commitHash);
    event RandomnessRevealed(uint256 randomValue);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice, uint256 _minParticipants) {
        owner = msg.sender;
        ticketPrice = _ticketPrice;
        minParticipants = _minParticipants > 0 ? _minParticipants : 3;
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

    /// @notice Commit randomness seed before round ends. Must be revealed after roundEnd.
    /// @param hash keccak256(seed) where seed will be revealed later.
    function commitRandomness(bytes32 hash) external onlyOwner {
        require(roundEnd > 0, "No active round");
        require(!committed, "Already committed");
        commitHash = hash;
        committed = true;
        emit RandomnessCommitted(hash);
    }

    /// @notice Reveal randomness seed and draw winner. Only callable after roundEnd.
    /// @param seed The preimage of the committed hash.
    function revealAndDraw(uint256 seed) external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(committed, "No randomness committed");
        require(keccak256(abi.encodePacked(seed)) == commitHash, "Invalid seed");
        require(players.length >= minParticipants, "Insufficient participants - cancel instead");

        uint256 randomValue = uint256(keccak256(abi.encodePacked(seed, block.number))) % players.length;
        emit RandomnessRevealed(randomValue);

        address winner = players[randomValue];
        roundWinners[currentRound] = winner;

        uint256 prize = address(this).balance;
        roundEnd = 0;
        committed = false;
        commitHash = bytes32(0);

        // Handle ETH-rejecting winners gracefully via try/catch pattern
        (bool sent, ) = winner.call{value: prize}("");
        if (!sent) {
            // If winner rejects ETH, hold prize for manual withdrawal or burn
            // For safety, transfer back to owner who can redistribute
            (bool ownerSent, ) = owner.call{value: prize}("");
            require(ownerSent, "Owner transfer also failed");
        }

        emit WinnerSelected(winner, prize, currentRound);
    }

    /// @notice Cancel the current round if deadline passed without enough participants.
    function cancelLottery() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round still active");
        require(players.length < minParticipants, "Enough participants");
        require(roundEnd > 0, "No active round");

        emit LotteryCancelled(currentRound, players.length);
        roundEnd = 0;
        committed = false;
        commitHash = bytes32(0);
    }

    /// @notice Claim refund for a cancelled round.
    function claimRefund() external {
        require(roundEnd == 0, "Round not cancelled");
        require(!refunded[currentRound][msg.sender], "Already refunded");

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
