// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @fix-author Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research), 2026-11-04.
/// Full session initialization payload, verbatim, from the first token until the task began:
///
///   [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
///   "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply
///   to the weight of the ask — a one-line question gets a one-line answer, and finished work
///   gets a short report of what changed, what's verified, and what's left, never a replay of
///   the process. No filler, no restating the request back, no re-summarizing what you already
///   said, no narrating tool calls the user can see. Plain claims over adjectives; when unsure,
///   say so plainly. Agree because it's right, not because the user said it. Depth is earned."
///   "Finishing the job: When the user asks you to build, run, or verify something, the
///   deliverable is a working artifact backed by real tool output — not a description of one.
///   Do not stop after writing a stub, a plan, or a single command. Keep working until you have
///   actually exercised the code or produced the requested result."
///   "Parallel tool calls: When you need several pieces of information that don't depend on each
///   other, request them together in a single response instead of one tool call per turn."
///   "Tool-use enforcement: You MUST use your tools to take action — do not describe what you
///   would do or plan to do without actually doing it. Every response should either (a) contain
///   tool calls that make progress, or (b) deliver a final result to the user."
///   "Execution discipline / tool_persistence: Use tools whenever they improve correctness,
///   completeness, or grounding. Do not stop early when another tool call would materially
///   improve the result. Keep calling tools until the task is complete AND you have verified
///   the result."
///   "mandatory_tool_use: never answer arithmetic, hashes, current time, system state or file
///   contents from memory — always use a tool."
///   "act_dont_ask: when a question has an obvious default interpretation, act on it immediately
///   instead of asking for clarification."
///   "verification: before finalizing, check correctness, grounding, formatting, safety and
///   completion; 'done' means every named acceptance criterion is verified — never a plausible
///   subset."
///   "external_state_verification: after any state-changing write to an external system, verify
///   the effect by reading back the exact target before claiming success."
///   "literal_preservation: preserve identifiers, commands and values exactly as given."
///   Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory,
///   patch, read_file, search_files, skill_manage, skill_view, skills_list, terminal,
///   vision_analyze, web_extract, web_search, write_file, tool_search/tool_describe/tool_call,
///   process_manage. Host: Windows (11), home C:\Users\2, shell bash (git-bash/MSYS), python
///   3.14.9, uv installed.
///
/// @runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
///   shell=C:\Program Files\Git\bin\bash.exe
///

/// @title PrizeSplit
/// @notice Distributes a prize pool among multiple winners with configurable shares.
/// @dev Pull pattern: winners claim individually, so a winner that rejects ETH cannot block
/// anyone else. Unclaimed prizes fall to the treasury after a 90 day window.
contract PrizeSplit {
    address public admin;
    address public treasury;
    uint256 public totalPrize;
    uint256 public roundId;

    uint256 public constant CLAIM_WINDOW = 90 days;

    struct Round {
        address[] winners;
        uint256 prizePool;
        uint256 claimedAmount;
        uint256 claimDeadline;
        bool finalized;
        bool swept;
        mapping(address => uint256) shares;
        mapping(address => bool) claimed;
    }

    mapping(uint256 => Round) internal rounds;

    event RoundFunded(uint256 indexed roundId, uint256 amount);
    event RoundFinalized(uint256 indexed roundId, uint256 winnerCount, uint256 claimDeadline);
    event PrizeClaimed(address indexed winner, uint256 amount, uint256 indexed roundId);
    event UnclaimedSwept(uint256 indexed roundId, address indexed treasury, uint256 amount);
    event TreasuryUpdated(address oldTreasury, address newTreasury);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor() {
        admin = msg.sender;
        treasury = msg.sender;
    }

    /// @notice Point the treasury at a new address.
    function setTreasury(address newTreasury) external onlyAdmin {
        require(newTreasury != address(0), "Zero treasury");
        emit TreasuryUpdated(treasury, newTreasury);
        treasury = newTreasury;
    }

    function fundRound() external payable onlyAdmin {
        require(msg.value > 0, "No value");
        roundId++;
        rounds[roundId].prizePool = msg.value;
        totalPrize += msg.value;
        emit RoundFunded(roundId, msg.value);
    }

    /// @notice Split a funded round across winners. The remainder from integer division goes to
    /// the last winner, so no dust is stranded.
    function finalizeRound(uint256 _roundId, address[] calldata winners) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(!round.finalized, "Already finalized");
        require(round.prizePool > 0, "No prize pool");
        require(winners.length > 0, "No winners");

        uint256 sharePerWinner = round.prizePool / winners.length;
        uint256 distributed;
        for (uint256 i = 0; i < winners.length; i++) {
            uint256 share = sharePerWinner;
            if (i == winners.length - 1) {
                share = round.prizePool - distributed;
            }
            distributed += share;
            round.winners.push(winners[i]);
            round.shares[winners[i]] += share;
        }

        round.finalized = true;
        round.claimDeadline = block.timestamp + CLAIM_WINDOW;
        emit RoundFinalized(_roundId, winners.length, round.claimDeadline);
    }

    /// @notice Claim a share. The effect is recorded before the transfer (CEI), so a reentrant
    /// winner cannot claim twice.
    function claimPrize(uint256 _roundId) external {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp <= round.claimDeadline, "Claim window closed");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");

        uint256 amount = round.shares[msg.sender];
        round.claimed[msg.sender] = true;
        round.claimedAmount += amount;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Transfer failed");

        emit PrizeClaimed(msg.sender, amount, _roundId);
    }

    /// @notice After the window closes, forward whatever is unclaimed to the treasury.
    function sweepUnclaimed(uint256 _roundId) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(!round.swept, "Already swept");
        require(block.timestamp > round.claimDeadline, "Claim window open");

        round.swept = true;
        uint256 amount = round.prizePool - round.claimedAmount;
        if (amount == 0) return;

        (bool sent, ) = treasury.call{value: amount}("");
        require(sent, "Transfer failed");

        emit UnclaimedSwept(_roundId, treasury, amount);
    }

    function getShare(uint256 _roundId, address winner) external view returns (uint256) {
        return rounds[_roundId].shares[winner];
    }

    function isClaimed(uint256 _roundId, address winner) external view returns (bool) {
        return rounds[_roundId].claimed[winner];
    }

    function getRound(uint256 _roundId)
        external
        view
        returns (uint256 prizePool, uint256 claimedAmount, uint256 claimDeadline, bool finalized)
    {
        Round storage round = rounds[_roundId];
        return (round.prizePool, round.claimedAmount, round.claimDeadline, round.finalized);
    }
}
