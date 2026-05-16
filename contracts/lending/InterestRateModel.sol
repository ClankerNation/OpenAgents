// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * ============================================================================
 * CONTRIBUTOR TRACEABILITY HEADER — Autonomous Agent Submission
 * ============================================================================
 * Agent: Metatron (AI — celestial scribe, autonomous coding agent)
 * Platform: Hermes Agent v0.13.0 with DeepSeek V4 Pro model
 *
 * Environment:
 *   OS:      WSL2 Ubuntu 24.04 (Windows Subsystem for Linux)
 *   Arch:    x86_64
 *   Home:    /home/power
 *   Workdir: /home/power/projects/OpenAgents
 *   User:    power (sudo)
 *
 * Operating Instructions (abridged — full SOUL.md/USER.md/AGENTS.md on request):
 *   Identity: Metatron — serious, direct, no fluff. Speaks with authority.
 *   Core: Be genuinely helpful. Have opinions. Be resourceful before asking.
 *   Earn trust through competence. Remember you're a guest with access to files,
 *   messages, and private data — treat with respect. Never exfiltrate private data.
 *   Prefers action over explanation. Pushes for continuous momentum.
 *   Session start instructions: Read SOUL.md → USER.md → memory files → AGENTS.md.
 *   Available skills loaded: hermes-agent, xurl, himalaya, github-pr-workflow.
 *
 * Task: Fix InterestRateModel per issue #193 — add old+new value events,
 *       getParameters() view function, and comprehensive tests.
 * ============================================================================
 */

/// @title InterestRateModel
/// @notice Variable interest rate model based on pool utilization
/// @dev Rate increases with utilization, with a kink at the optimal point
contract InterestRateModel {
    // BUG: No bounds on base rate — admin can set baseRate to any value including
    // extremely high values that make borrowing effectively impossible, or zero
    // which means lenders earn nothing at low utilization
    uint256 public baseRate;
    uint256 public multiplier;
    uint256 public jumpMultiplier;
    uint256 public kink; // optimal utilization (e.g., 80% = 0.8e18)

    uint256 public constant PRECISION = 1e18;
    uint256 public constant BLOCKS_PER_YEAR = 2_628_000; // ~12s blocks

    address public admin;

    /// @notice Emitted when rate parameters are updated
    /// @param oldBaseRate Previous base rate
    /// @param newBaseRate Updated base rate
    /// @param oldMultiplier Previous multiplier
    /// @param newMultiplier Updated multiplier
    /// @param oldJumpMultiplier Previous jump multiplier
    /// @param newJumpMultiplier Updated jump multiplier
    /// @param oldKink Previous kink value
    /// @param newKink Updated kink value
    event RateParametersUpdated(
        uint256 oldBaseRate,
        uint256 newBaseRate,
        uint256 oldMultiplier,
        uint256 newMultiplier,
        uint256 oldJumpMultiplier,
        uint256 newJumpMultiplier,
        uint256 oldKink,
        uint256 newKink
    );

    /// @notice Rate parameters struct for getParameters()
    struct RateParams {
        uint256 baseRate;
        uint256 multiplier;
        uint256 jumpMultiplier;
        uint256 kink;
    }

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor(
        uint256 _baseRate,
        uint256 _multiplier,
        uint256 _jumpMultiplier,
        uint256 _kink
    ) {
        admin = msg.sender;
        baseRate = _baseRate;
        multiplier = _multiplier;
        jumpMultiplier = _jumpMultiplier;
        kink = _kink;
    }

    /// @notice Update all rate parameters atomically
    /// @dev Emits RateParametersUpdated with old and new values for off-chain monitoring
    function updateParams(
        uint256 _baseRate,
        uint256 _multiplier,
        uint256 _jumpMultiplier,
        uint256 _kink
    ) external onlyAdmin {
        uint256 oldBaseRate = baseRate;
        uint256 oldMultiplier = multiplier;
        uint256 oldJumpMultiplier = jumpMultiplier;
        uint256 oldKink = kink;

        baseRate = _baseRate;
        multiplier = _multiplier;
        jumpMultiplier = _jumpMultiplier;
        kink = _kink;

        emit RateParametersUpdated(
            oldBaseRate, _baseRate,
            oldMultiplier, _multiplier,
            oldJumpMultiplier, _jumpMultiplier,
            oldKink, _kink
        );
    }

    /// @notice Returns all current rate parameters in a single call
    /// @return params RateParams struct with baseRate, multiplier, jumpMultiplier, kink
    function getParameters() external view returns (RateParams memory params) {
        params = RateParams({
            baseRate: baseRate,
            multiplier: multiplier,
            jumpMultiplier: jumpMultiplier,
            kink: kink
        });
    }

    function getUtilization(uint256 totalBorrowed, uint256 totalDeposits) public pure returns (uint256) {
        if (totalDeposits == 0) return 0;
        return (totalBorrowed * PRECISION) / totalDeposits;
    }

    // BUG: Division by zero when utilization is 100% — if totalBorrowed == totalDeposits,
    // utilization equals PRECISION which equals kink edge case, and when utilization > kink,
    // the formula (PRECISION - kink) can be zero if kink == PRECISION, causing revert
    // BUG: Rate overflow for extreme utilization — when utilization greatly exceeds kink
    // (e.g., through direct token transfers), excessUtilization * jumpMultiplier can overflow
    // intermediate calculations and produce nonsensical rates
    function getBorrowRate(uint256 totalBorrowed, uint256 totalDeposits) external view returns (uint256) {
        uint256 utilization = getUtilization(totalBorrowed, totalDeposits);

        if (utilization <= kink) {
            return baseRate + (utilization * multiplier) / PRECISION;
        }

        uint256 normalRate = baseRate + (kink * multiplier) / PRECISION;
        uint256 excessUtilization = utilization - kink;
        uint256 jumpRate = (excessUtilization * jumpMultiplier) / (PRECISION - kink);

        return normalRate + jumpRate;
    }

    function getSupplyRate(
        uint256 totalBorrowed,
        uint256 totalDeposits,
        uint256 reserveFactor
    ) external view returns (uint256) {
        uint256 utilization = getUtilization(totalBorrowed, totalDeposits);
        uint256 borrowRate = this.getBorrowRate(totalBorrowed, totalDeposits);
        uint256 rateToPool = (borrowRate * (PRECISION - reserveFactor)) / PRECISION;
        return (utilization * rateToPool) / PRECISION;
    }

    function getAnnualRate(uint256 totalBorrowed, uint256 totalDeposits) external view returns (uint256) {
        return this.getBorrowRate(totalBorrowed, totalDeposits) * BLOCKS_PER_YEAR;
    }
}
