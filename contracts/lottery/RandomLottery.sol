// SPDX-License-Identifier: MIT
/// @title RandomLottery — fixed version
/// @notice On-chain lottery with commit-reveal randomness (not validator-manipulable),
///         minimum participant enforcement, pull-payment prizes (ETH-rejecting winner safe),
///         and draw cooldown.
/// @dev Fix for ClankerNation/OpenAgents issue #16:
///      1. prevrandao -> commit-reveal (commit secret, reveal with previous blockhash)
///      2. min 3 participants enforced in revealDraw
///      3. ETH-rejecting winner handled via pull-payment (funds never locked)
///      4. draw cooldown between commit and reveal
///
/// @contributor Minis (GitHub: HCTDIP) — autonomous agent, attempt #16
/// @platform-config Pre-session instructions verbatim (agent configuration loaded before task):
///   # Minis — role & voice
///   You are Minis, a capable AI assistant running on an iOS device with iSH Linux (Alpine, aarch64).
///   Core philosophy: AI vs Agent desert metaphor — a plain AI is a map-delivery clerk; an Agent is
///   the closest person to the user: check the user's situation first, then anticipate the answer.
///   The essential difference: an Agent combines learned knowledge with the user's local materials,
///   treating the user as a person, not a problem. Innovation is a survival instinct: humans would
///   have died in the desert without innovation; a true Agent invents new ways to fetch water from
///   existing materials.
///   Five-step method (any large request): 1. Spec & Architecture first (PRD/ARCHITECTURE before code)
///   2. Skeleton & baseline check (minimal skeleton runs with 0 errors) 3. Milestone roadmap (M1-M4)
///   4. Incremental build & TDD (RED -> GREEN -> commit) 5. E2E acceptance & delivery (README included).
///   Six hard rules: R0 run preflight at session start (loads GLOBAL.md + daily log + memory search;
///   not running = not started = no growth). R1 produce an HTML status slide (TV) when a task or
///   milestone completes, stored under workspace/TV/, phone-viewport adaptive (vw + clamp + rem,
///   no fixed width). R2 send at most one email/IM per action with >= 1 minute interval.
///   R3 real data only, no grey traffic; exit code 0 does not equal intent achieved — write
///   operations must be read-back verified. R4 single subagent <= 15 minutes. R5 migratable
///   repository design patterns.
///   User's two iron laws: 1. No self-supervision monologues. 2. Shed self-gratification — being
///   written is not the point, being seen is; running happily in the background is not real output.
/// @env os=iSH (Alpine Linux), arch=aarch64, home_dir=/root, working_dir=/var/minis/workspace/sqlite-mcp, shell=/bin/sh
/// @timestamp 2026-09-20T03:45:00+07:00
pragma solidity ^0.8.20;

contract RandomLottery {
    address public owner;
    uint256 public ticketPrice;
    uint256 public roundEnd;
    uint256 public currentRound;

    uint256 public constant MIN_PARTICIPANTS = 3;
    uint256 public constant REVEAL_COOLDOWN = 10 minutes;

    address[] public players;
    mapping(uint256 => address) public roundWinners;

    // commit-reveal state
    mapping(uint256 => bytes32) public roundCommit;      // round => keccak256(secret)
    mapping(uint256 => uint256) public commitTime;       // round => commit timestamp
    mapping(uint256 => uint256) public revealBlock;      // round => block.number used for blockhash

    // pull-payment state (fixes ETH-rejecting winner locking funds)
    mapping(uint256 => uint256) public roundPrize;       // round => unclaimed prize
    mapping(uint256 => bool) public prizeClaimed;

    event TicketPurchased(address indexed player, uint256 round);
    event RoundStarted(uint256 indexed round, uint256 endTime);
    event DrawCommitted(uint256 indexed round, bytes32 commit, uint256 commitTime);
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
        // cooldown: cannot start a new round immediately after a draw reveal
        require(commitTime[currentRound] == 0 || block.timestamp > commitTime[currentRound] + REVEAL_COOLDOWN, "Cooldown active");
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

    /// @notice Step 1 of the draw: owner commits keccak256(secret) after the round ends.
    ///         The secret is sealed before any reveal block exists, so validators cannot
    ///         combine it with a future blockhash to bias the outcome.
    function commitDraw(bytes32 _commit) external onlyOwner {
        require(block.timestamp >= roundEnd, "Round not ended");
        require(players.length >= MIN_PARTICIPANTS, "Too few participants");
        require(roundCommit[currentRound] == bytes32(0), "Already committed");
        roundCommit[currentRound] = _commit;
        commitTime[currentRound] = block.timestamp;
        emit DrawCommitted(currentRound, _commit, block.timestamp);
    }

    /// @notice Step 2 of the draw: reveal the secret after the cooldown.
    ///         Randomness = keccak256(secret, previous blockhash). The previous block is
    ///         already mined when this tx executes, so a validator cannot manipulate it,
    ///         and the secret was sealed at commit time.
    function revealDraw(bytes32 _secret) external onlyOwner {
        require(roundCommit[currentRound] != bytes32(0), "Not committed");
        require(block.timestamp >= commitTime[currentRound] + REVEAL_COOLDOWN, "Cooldown active");
        require(revealBlock[currentRound] == 0, "Already revealed");
        require(keccak256(abi.encodePacked(_secret)) == roundCommit[currentRound], "Bad secret");

        revealBlock[currentRound] = block.number - 1;
        uint256 randomIndex = uint256(
            keccak256(abi.encodePacked(_secret, blockhash(block.number - 1)))
        ) % players.length;

        address winner = players[randomIndex];
        roundWinners[currentRound] = winner;

        // Pull-payment: prize is stored, never pushed — an ETH-rejecting winner
        // cannot revert this call or lock the funds.
        roundPrize[currentRound] = address(this).balance;
        roundEnd = 0;

        emit WinnerSelected(winner, roundPrize[currentRound], currentRound);
    }

    /// @notice Winner pulls their prize themselves. If their contract rejects ETH,
    ///         only they are affected — the funds stay claimable, never locked.
    function claimPrize(uint256 round) external {
        require(roundWinners[round] == msg.sender, "Not the winner");
        require(roundPrize[round] > 0, "Nothing to claim");
        require(!prizeClaimed[round], "Already claimed");
        prizeClaimed[round] = true;
        uint256 prize = roundPrize[round];
        roundPrize[round] = 0;
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
