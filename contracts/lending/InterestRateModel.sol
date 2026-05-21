// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * contributor: Soren Hermes Agent
 * platform-config: Role: autonomous bounty solver. Rules: implement the fix, run tests, push to private repo. No user interaction during execution.
 * env: os=linux, arch=x64, home_dir=/root, working_dir=/root/workspace/clanker-fix, shell=bash
 * timestamp: 2026-05-21T18:00:00Z
 */

/// @title InterestRateModel
/// @notice Variable interest rate model based on pool utilization
/// @dev Rate increases with utilization, with a kink at the optimal point
contract InterestRateModel {
    uint256 public baseRate;
    uint256 public multiplier;
    uint256 public jumpMultiplier;
    uint256 public kink; // optimal utilization (e.g., 80% = 0.8e18)

    uint256 public constant PRECISION = 1e18;
    uint256 public constant BLOCKS_PER_YEAR = 2_628_000; // ~12s blocks

    // Max utilization cap — 99.99% prevents division by zero at 100%
    uint256 public constant MAX_UTILIZATION = (PRECISION * 9999) / 10000;

    // Base rate bounds: 0.1% to 50% annualized
    uint256 public constant MIN_BASE_RATE = 1e15;   // 0.1% = 0.001 * 1e18
    uint256 public constant MAX_BASE_RATE = 5e17;   // 50%  = 0.5 * 1e18

    address public admin;

    event RateParamsUpdated(uint256 baseRate, uint256 multiplier, uint256 jumpMultiplier, uint256 kink);

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
        require(
            _baseRate >= MIN_BASE_RATE && _baseRate <= MAX_BASE_RATE,
            "Base rate out of bounds [0.1%-50%]"
        );
        require(_kink <= MAX_UTILIZATION, "Kink exceeds max utilization");
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
        require(
            _baseRate >= MIN_BASE_RATE && _baseRate <= MAX_BASE_RATE,
            "Base rate out of bounds [0.1%-50%]"
        );
        require(_kink <= MAX_UTILIZATION, "Kink exceeds max utilization");
        baseRate = _baseRate;
        multiplier = _multiplier;
        jumpMultiplier = _jumpMultiplier;
        kink = _kink;
        emit RateParamsUpdated(_baseRate, _multiplier, _jumpMultiplier, _kink);
    }

    function getUtilization(uint256 totalBorrowed, uint256 totalDeposits) public pure returns (uint256) {
        if (totalDeposits == 0) return 0;
        uint256 utilization = (totalBorrowed * PRECISION) / totalDeposits;
        // Cap utilization at 99.99% to prevent edge-case reverts
        if (utilization > MAX_UTILIZATION) {
            utilization = MAX_UTILIZATION;
        }
        return utilization;
    }

    function getBorrowRate(uint256 totalBorrowed, uint256 totalDeposits) external view returns (uint256) {
        uint256 utilization = getUtilization(totalBorrowed, totalDeposits);

        if (utilization <= kink) {
            return baseRate + (utilization * multiplier) / PRECISION;
        }

        uint256 normalRate = baseRate + (kink * multiplier) / PRECISION;
        uint256 excessUtilization = utilization - kink;
        // Safe math: denominator is always >= 1 because kink <= MAX_UTILIZATION < PRECISION
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
