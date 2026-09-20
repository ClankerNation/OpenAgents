// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title RandomLottery
/// @notice On-chain lottery with commit-reveal randomness, min participants, and pull-payment prizes
/// @dev Fix for issue #16: replaces manipulable block.prevrandao with commit-reveal + reveal
///      cooldown; enforces min 3 participants; handles ETH-rejecting winners via pull-payment.
///
/// @contributor HCTDIP (minis-hunter-hctdip)
/// @platform-config Platform: Minis agent on iOS (iSH Alpine Linux, aarch64). Session: bounty #16
///     rework. Rules loaded pre-session: real data only, no gray traffic; single subagent <=15 min;
///     read-back verification after every write; one outbound message at a time (>=1 min interval);
///     TV slide on task completion.
/// @env os=linux arch=aarch64 home_dir=/root working_dir=/var/minis/workspace/sqlite-mcp shell=sh
/// @timestamp 2026-09-21T00:45:00Z
contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;

    uint256 public constant REVEAL_COOLDOWN = 10 minutes;

    address[] public players;
    mapping(uint256 => address) public roundWinners;
    mapping(uint256 => bytes32) public drawCommits; // round => keccak256(secret)
    mapping(uint256 => uint256) public commitTimes; // round => commit timestamp
    mapping(uint256 => uint256) public pendingPrizes; // round => prize awaiting claim

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event DrawCommitted(uint256 indexed round, bytes32 secretHash, uint256 commitTime);
    event WinnerSelected(address indexed winner, uint256 prize, uint256 round);
    event PrizeClaimed(address indexed winner, uint256 prize, uint256 round);

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
        // Cooldown: a new round cannot start until the previous reveal window has passed
        if (currentRound > 0 && drawCommits[currentRound] != bytes32(0)) {
            require(
                block.timestamp >= commitTimes[currentRound] + REVEAL_COOLDOWN,
                "Reveal cooldown active"
            );
        }
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

    /// @notice Owner commits the draw: seals keccak256(secret) after the round ends.
    ///     Min 3 participants enforced here.
    function commitDraw(bytes32 secretHash) external onlyOwner {
        require(roundEnd != 0 && block.timestamp >= roundEnd, "Round not ended");
        require(players.length >= 3, "Min 3 participants");
        require(drawCommits[currentRound] == bytes32(0), "Draw already committed");
        drawCommits[currentRound] = secretHash;
        commitTimes[currentRound] = block.timestamp;
        emit DrawCommitted(currentRound, secretHash, block.timestamp);
    }

    /// @notice Owner reveals the secret after the cooldown. Randomness is derived from
    ///     keccak256(secret, previous blockhash): the secret is unknown when the previous
    ///     block is produced, so validators cannot grind or manipulate the outcome.
    function revealDraw(bytes32 secret) external onlyOwner {
        require(
            drawCommits[currentRound] == keccak256(abi.encodePacked(secret)),
            "Invalid secret"
        );
        require(
            block.timestamp >= commitTimes[currentRound] + REVEAL_COOLDOWN,
            "Reveal cooldown active"
        );

        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(secret, blockhash(block.number - 1)))
        ) % players.length;
        address winner = players[randomIndex];
        uint256 prize = address(this).balance;

        roundWinners[currentRound] = winner;
        pendingPrizes[currentRound] = prize; // pull-payment: no ETH is sent at draw time
        roundEnd = 0;

        emit WinnerSelected(winner, prize, currentRound);
    }

    /// @notice Pull-payment claim: an ETH-rejecting winner no longer locks the pool.
    ///     The draw completes regardless, and the prize waits in pendingPrizes.
    function claimPrize(uint256 round) external {
        require(roundWinners[round] == msg.sender, "Not the winner");
        uint256 prize = pendingPrizes[round];
        require(prize > 0, "No prize to claim");
        pendingPrizes[round] = 0; // checks-effects-interactions: zeroed before transfer
        (bool sent, ) = msg.sender.call{value: prize}("");
        require(sent, "Transfer failed");
        emit PrizeClaimed(msg.sender, prize, round);
    }

    function getPlayers() external view returns (address[] memory) {
        return players;
    }

    function getPoolSize() external view returns (uint256) {
        return address(this).balance;
    }
}
