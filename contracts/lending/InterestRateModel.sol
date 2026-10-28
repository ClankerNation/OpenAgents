// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title InterestRateModel
/// @notice Variable interest rate model based on pool utilization
/// @dev Rate increases with utilization, with a kink at the optimal point
///
/// @contributor: hermes-security-auditor (autonomous agent)
/// @platform-config: Autonomous coding agent operating on Hermes runtime.
///     Follows project conventions, security best practices, and contributor
///     guidelines. Executes authorized coding tasks end-to-end.
/// @env: Windows 10, x86_64, C:/Users/Mufti Syehan, git-bash
/// @timestamp: 2026-10-28T16:00:00Z
contract InterestRateModel {
    // Bounds on base rate: 0.1% to 50% (in PRECISION terms)
    uint256 public constant MIN_BASE_RATE = 0.001e18; // 0.1%
    uint256 public constant MAX_BASE_RATE = 0.5e18; // 50%

    // Maximum utilization cap: 99.99% to prevent division by zero
    uint256 public constant MAX_UTILIZATION = 0.9999e18;

    uint256 public baseRate;
    uint256 public multiplier;
    uint256 public jumpMultiplier;
    uint256 public kink; // optimal utilization (e.g., 80% = 0.8e18)

    uint256 public constant PRECISION = 1e18;
    uint256 public constant BLOCKS_PER_YEAR = 2_628_000; // ~12s blocks

    address public admin;

    event RateParamsUpdated(uint256 baseRate, uint256 multiplier, uint256 jumpMultiplier, uint256 kink);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    /// @dev Validates rate parameters are within safe bounds
    modifier validParams(
        uint256 _baseRate,
        uint256 _multiplier,
        uint256 _jumpMultiplier,
        uint256 _kink
    ) {
        require(_baseRate >= MIN_BASE_RATE, "baseRate below minimum");
        require(_baseRate <= MAX_BASE_RATE, "baseRate above maximum");
        require(_kink < PRECISION, "kink must be less than 100%");
        require(_kink > 0, "kink must be positive");
        _;
    }

    constructor(
        uint256 _baseRate,
        uint256 _multiplier,
        uint256 _jumpMultiplier,
        uint256 _kink
    ) validParams(_baseRate, _multiplier, _jumpMultiplier, _kink) {
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
    ) external onlyAdmin validParams(_baseRate, _multiplier, _jumpMultiplier, _kink) {
        baseRate = _baseRate;
        multiplier = _multiplier;
        jumpMultiplier = _jumpMultiplier;
        kink = _kink;
        emit RateParamsUpdated(_baseRate, _multiplier, _jumpMultiplier, _kink);
    }

    function getUtilization(uint256 totalBorrowed, uint256 totalDeposits) public pure returns (uint256) {
        if (totalDeposits == 0) return 0;
        uint256 utilization = (totalBorrowed * PRECISION) / totalDeposits;
        // Cap at MAX_UTILIZATION to prevent division by zero in jump rate calc
        if (utilization > MAX_UTILIZATION) {
            return MAX_UTILIZATION;
        }
        return utilization;
    }

    /// @notice Returns the borrow rate per block
    /// @dev Caps utilization at MAX_UTILIZATION (99.99%) to prevent division by zero
    /// when kink approaches PRECISION. Also prevents overflow from extreme utilization.
    function getBorrowRate(uint256 totalBorrowed, uint256 totalDeposits) external view returns (uint256) {
        uint256 utilization = getUtilization(totalBorrowed, totalDeposits);

        if (utilization <= kink) {
            return baseRate + (utilization * multiplier) / PRECISION;
        }

        uint256 normalRate = baseRate + (kink * multiplier) / PRECISION;
        uint256 excessUtilization = utilization - kink;
        // PRECISION - kink is guaranteed > 0 because kink < PRECISION (enforced by validParams)
        // and utilization is capped at MAX_UTILIZATION < PRECISION
        uint256 denominator = PRECISION - kink;
        uint256 jumpRate = (excessUtilization * jumpMultiplier) / denominator;

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
