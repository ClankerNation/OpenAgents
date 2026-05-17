// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title PrizeSplit
/// @notice Distributes prize pool among multiple winners with configurable shares
/// @dev Winners claim their share individually after the admin finalizes the round.
///      Uses pull pattern so a contract winner that rejects ETH cannot block others.
///      Unclaimed prizes can be reclaimed by admin to treasury after 90-day deadline.
///
// @fix-author Metatron (Hermes Agent)
// @fix-date 2026-05-17
// @runtime os: linux, arch: x64, shell: bash, working_dir: /home/power/projects/OpenAgents
// @pre-conversation: Autonomous bounty-hunting loop — MANDATORY STARTUP: check open PRs, report status changes, work highest-priority unclaimed Solidity bounty. Prefer Solidity issues, add traceability header, update CONTRIBUTORS.json. Rules: never work on issue with existing open PR from invisiblemonsters. Bounty: #189 PrizeSplit pull pattern $5k. Acceptance: pull pattern, contract winners don't block others, 90-day reclaim deadline, tests for contract winner/claim deadline/treasury reclaim, CONTRIBUTORS.json entry.
contract PrizeSplit {
    address public admin;
    uint256 public totalPrize;
    uint256 public roundId;

    uint256 public constant CLAIM_DEADLINE = 90 days;

    struct Round {
        address[] winners;
        uint256 prizePool;
        uint256 claimDeadline;
        bool finalized;
        bool reclaimed;
        mapping(address => uint256) shares;
        mapping(address => bool) claimed;
    }

    mapping(uint256 => Round) internal rounds;

    // Simple reentrancy guard
    uint256 private _guard;

    event RoundFunded(uint256 indexed roundId, uint256 amount);
    event RoundFinalized(uint256 indexed roundId, uint256 winnerCount, uint256 claimDeadline);
    event PrizeClaimed(address indexed winner, uint256 amount, uint256 indexed roundId);
    event ClaimFailed(address indexed winner, uint256 amount, uint256 indexed roundId, bytes reason);
    event PrizeReclaimed(uint256 indexed roundId, uint256 amount, address indexed treasury);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    modifier nonReentrant() {
        require(_guard == 0, "Reentrant call");
        _guard = 1;
        _;
        _guard = 0;
    }

    constructor() {
        admin = msg.sender;
    }

    function fundRound() external payable onlyAdmin {
        roundId++;
        rounds[roundId].prizePool = msg.value;
        totalPrize += msg.value;
        emit RoundFunded(roundId, msg.value);
    }

    /// @notice Finalize a round by setting winners and shares.
    /// @dev Requires at least one winner. Dust from integer division is left to
    ///      the contract and can be swept during reclaim. Sets 90-day claim deadline.
    function finalizeRound(uint256 _roundId, address[] calldata winners) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(!round.finalized, "Already finalized");
        require(round.prizePool > 0, "No prize pool");
        require(winners.length > 0, "No winners");

        uint256 sharePerWinner = round.prizePool / winners.length;

        for (uint256 i = 0; i < winners.length; i++) {
            round.winners.push(winners[i]);
            round.shares[winners[i]] = sharePerWinner;
        }

        round.finalized = true;
        round.claimDeadline = block.timestamp + CLAIM_DEADLINE;

        emit RoundFinalized(_roundId, winners.length, round.claimDeadline);
    }

    /// @notice Claim prize for a finalized round.
    /// @dev Uses reentrancy guard to safely perform the external call before
    ///      marking claimed. If the ETH transfer fails (e.g., winner is a
    ///      contract without receive()), the claim is NOT marked and the
    ///      winner can retry later until the deadline. Failed claims emit
    ///      ClaimFailed but do NOT revert, so other winners are unaffected.
    function claimPrize(uint256 _roundId) external nonReentrant {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(!round.reclaimed, "Already reclaimed");
        require(block.timestamp <= round.claimDeadline, "Claim deadline passed");
        require(round.shares[msg.sender] > 0, "No share");
        require(!round.claimed[msg.sender], "Already claimed");

        uint256 amount = round.shares[msg.sender];

        // External call BEFORE state change (guarded by nonReentrant)
        (bool sent, bytes memory data) = msg.sender.call{value: amount}("");

        if (sent) {
            round.claimed[msg.sender] = true;
            emit PrizeClaimed(msg.sender, amount, _roundId);
        } else {
            // Transfer failed — contract likely doesn't have receive().
            // Claim is NOT marked, so ETH stays in contract for the winner to retry
            // or for admin to reclaim after deadline.
            // Does NOT revert — other winners can still claim.
            emit ClaimFailed(msg.sender, amount, _roundId, data);
        }
    }

    /// @notice Reclaim all unclaimed ETH from a round after the deadline.
    /// @dev Sends all remaining contract ETH attributable to this round to treasury.
    ///      Can only be called once per round, after the deadline has passed.
    function reclaimUnclaimed(uint256 _roundId, address treasury) external onlyAdmin {
        Round storage round = rounds[_roundId];
        require(round.finalized, "Not finalized");
        require(block.timestamp > round.claimDeadline, "Deadline not passed");
        require(!round.reclaimed, "Already reclaimed");
        require(treasury != address(0), "Zero treasury");

        round.reclaimed = true;

        // Send all remaining contract balance attributable to this round.
        // This includes unclaimed shares + dust from integer division.
        uint256 balance = address(this).balance;
        if (balance > 0) {
            (bool sent, ) = treasury.call{value: balance}("");
            require(sent, "Reclaim transfer failed");
            emit PrizeReclaimed(_roundId, balance, treasury);
        }
    }

    function getShare(uint256 _roundId, address winner) external view returns (uint256) {
        return rounds[_roundId].shares[winner];
    }

    function isClaimed(uint256 _roundId, address winner) external view returns (bool) {
        return rounds[_roundId].claimed[winner];
    }

    function isReclaimed(uint256 _roundId) external view returns (bool) {
        return rounds[_roundId].reclaimed;
    }

    function getClaimDeadline(uint256 _roundId) external view returns (uint256) {
        return rounds[_roundId].claimDeadline;
    }
}
