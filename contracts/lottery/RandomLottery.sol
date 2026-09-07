// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RandomLottery
/// @notice On-chain lottery using block.prevrandao for randomness
/// @dev Players buy tickets, and a random winner is selected after the round ends.
///      Bounty #167 fix: added lottery deadline + cancel + refund mechanism
///      so participants can recover funds if the lottery doesn't reach minimum participants.
/// @contributor: Hermes Agent (hummern)
/// @platform-config: Hermes Agent by Nous Research — autonomous coding agent; all skills and tools available; GitHub bounties via gh CLI; Solana CLI in PATH; local Ollama and vLLM servers; Kaggle GPU training; Tailscale tunneled services; EVM payout address 0x01d830d1e147e36eaaf3697b71923c3959c8a85e; DCO signoff required; earnings-first publishing.
/// @runtime: os=linux, arch=x64, home_dir=/home/kloa, working_dir=/home/kloa, shell=bash
/// @timestamp: 2026-09-07
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;
    uint256 public defaultMinParticipants;

    address[] public players;
    mapping(uint256 => address) public roundWinners;

    // Bounty #167: per-round state for refunds + cancellation
    struct Round {
        uint256 deadline;            // absolute timestamp; cancellation becomes possible after this
        uint256 minParticipants;     // required minimum participants for this round
        bool cancelled;              // true after cancelLottery()
        bool completed;              // true after drawWinner()
        address[] participants;      // snapshot of all players for this round
        mapping(address => uint256) contributions; // player => ETH contributed this round
        mapping(address => bool) refunded;         // player => already-refunded flag
    }
    mapping(uint256 => Round) public rounds;

    event TicketPurchased(address indexed player, uint256 round, uint256 amount);
    event RoundStarted(uint256 indexed round, uint256 endTime, uint256 minParticipants);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event LotteryCancelled(uint256 indexed round);
    event RefundIssued(address indexed player, uint256 indexed round, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(uint256 _ticketPrice, uint256 _defaultMinParticipants) {
        require(_defaultMinParticipants > 0, "RandomLottery: minParticipants must be > 0");
        owner = msg.sender;
        ticketPrice = _ticketPrice;
        defaultMinParticipants = _defaultMinParticipants;
    }

    /// @notice Start a new lottery round.
    /// @param duration How long the round runs (seconds).
    /// @param customMinParticipants Override the default min participants for this round
    ///        (set to 0 to use the default).
    function startRound(uint256 duration, uint256 customMinParticipants) external onlyOwner {
        require(roundEnd == 0 || block.timestamp > roundEnd, "Round active");
        require(customMinParticipants != 1, "RandomLottery: minParticipants must be 0 or >= 2");

        delete players;
        currentRound++;
        roundEnd = block.timestamp + duration;

        uint256 minP = customMinParticipants == 0 ? defaultMinParticipants : customMinParticipants;
        require(minP >= 2, "RandomLottery: minParticipants must be >= 2");

        Round storage r = rounds[currentRound];
        r.deadline = roundEnd;
        r.minParticipants = minP;
        r.cancelled = false;
        r.completed = false;

        emit RoundStarted(currentRound, roundEnd, minP);
    }

    function buyTicket() external payable {
        require(block.timestamp < roundEnd, "Round ended");
        require(msg.value == ticketPrice, "Wrong ticket price");

        Round storage r = rounds[currentRound];
        require(!r.cancelled, "Round cancelled");
        require(!r.completed, "Round completed");

        players.push(msg.sender);
        r.participants.push(msg.sender);
        r.contributions[msg.sender] += msg.value;
        emit TicketPurchased(msg.sender, currentRound, msg.value);
    }

    function drawWinner() external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length >= defaultMinParticipants, "Below min participants; cancel instead");

        Round storage r = rounds[currentRound];
        require(!r.cancelled, "Round cancelled");
        require(!r.completed, "Already drawn");
        r.completed = true;

        // BUG: prevrandao is manipulable by validators — validators can influence
        // the randomness value, making the lottery outcome predictable/riggable
        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(block.prevrandao, block.timestamp))
        ) % players.length;

        // BUG: No minimum participants check — if only 1 player entered,
        // the lottery is pointless and the single player always wins their own funds minus gas
        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        uint256 prize = address(this).balance;
        roundEnd = 0;

        // BUG: Winner can be a contract that rejects ETH (no receive/fallback),
        // causing this call to revert and locking all funds permanently
        (bool sent, ) = winner.call{value: prize}("");
        require(sent, "Transfer failed");

        emit WinnerSelected(winner, prize, currentRound);
    }

    /// @notice Bounty #167 fix: cancel a lottery round after deadline.
    /// @dev Can only be called by owner. The round must have ended without reaching
    ///      minParticipants, and the round must not have been previously cancelled
    ///      or completed.
    function cancelLottery(uint256 roundId) external onlyOwner {
        Round storage r = rounds[roundId];
        require(!r.cancelled, "Already cancelled");
        require(!r.completed, "Already completed");
        require(block.timestamp >= r.deadline, "Round not ended yet");
        require(
            r.participants.length < r.minParticipants,
            "Round reached min participants; cannot cancel"
        );
        r.cancelled = true;
        emit LotteryCancelled(roundId);
    }

    /// @notice Bounty #167 fix: refund a participant's contribution after cancellation.
    /// @dev Each participant can only refund their own contribution once.
    /// @param roundId The round to refund from.
    function refund(uint256 roundId) external {
        Round storage r = rounds[roundId];
        require(r.cancelled, "Round not cancelled");
        require(!r.refunded[msg.sender], "Already refunded");
        uint256 amount = r.contributions[msg.sender];
        require(amount > 0, "No contribution");

        r.refunded[msg.sender] = true;
        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Refund transfer failed");

        emit RefundIssued(msg.sender, roundId, amount);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }

    function getRoundParticipants(uint256 roundId) external view returns (address[] memory) {
        return rounds[roundId].participants;
    }

    function getRoundInfo(uint256 roundId) external view returns (
        uint256 deadline,
        uint256 minParticipants_,
        bool cancelled,
        bool completed,
        uint256 participantCount
    ) {
        Round storage r = rounds[roundId];
        return (
            r.deadline,
            r.minParticipants,
            r.cancelled,
            r.completed,
            r.participants.length
        );
    }
}
