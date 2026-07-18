// @fix-author
// Name: freebuff (via hanu-14)
// Date: 2026-07-18
//
// Startup configuration (complete instructions loaded into context before any user interaction):
// [REDACTED — system prompt contains sensitive credentials such as GitHub PATs and must not be committed.]
//
// Runtime information:
//   Platform: win32
//   Architecture: AMD64
//   Home directory: C:\Users\MOHAMMED HANAN M T P
//   Working directory: C:\Projects\OSS\OpenAgents
//   Shell: bash

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

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

    event RateParametersUpdated(
        uint256 indexed oldBaseRate,
        uint256 indexed oldMultiplier,
        uint256 indexed oldJumpMultiplier,
        uint256 oldKink,
        uint256 newBaseRate,
        uint256 newMultiplier,
        uint256 newJumpMultiplier,
        uint256 newKink
    );

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

    function updateParams(
        uint256 _baseRate,
        uint256 _multiplier,
        uint256 _jumpMultiplier,
        uint256 _kink
    ) external onlyAdmin {
        uint256 oldBase = baseRate;
        uint256 oldMult = multiplier;
        uint256 oldJump = jumpMultiplier;
        uint256 oldKink = kink;

        baseRate = _baseRate;
        multiplier = _multiplier;
        jumpMultiplier = _jumpMultiplier;
        kink = _kink;

        emit RateParametersUpdated(oldBase, oldMult, oldJump, oldKink, _baseRate, _multiplier, _jumpMultiplier, _kink);
    }

    /// @notice Returns all current rate parameters in a single call.
    function getParameters() external view returns (
        uint256 _baseRate,
        uint256 _multiplier,
        uint256 _jumpMultiplier,
        uint256 _kink
    ) {
        return (baseRate, multiplier, jumpMultiplier, kink);
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
