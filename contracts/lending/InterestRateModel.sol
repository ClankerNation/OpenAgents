// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * Contributor traceability:
 * Agent: Codex
 * Timestamp: 2026-05-25T11:15:47Z
 * Runtime: os=Windows, arch=x64, home_dir=C:\Users\tupm96,
 * working_dir=C:\Users\tupm96\Desktop\bounty\OpenAgents, shell=powershell
 * Private platform, system, and developer instructions are not disclosed.
 */

/// @title InterestRateModel
/// @notice Variable interest rate model based on pool utilization
/// @dev Rate increases with utilization, with a kink at the optimal point.
contract InterestRateModel {
    uint256 public baseRate;
    uint256 public multiplier;
    uint256 public jumpMultiplier;
    uint256 public kink;

    uint256 public constant PRECISION = 1e18;
    uint256 public constant BLOCKS_PER_YEAR = 2_628_000; // ~12s blocks
    uint256 public constant MIN_BASE_RATE = 0.001e18; // 0.1%
    uint256 public constant MAX_BASE_RATE = 0.5e18; // 50%
    uint256 public constant MAX_UTILIZATION = 0.9999e18; // 99.99%

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
        _validateParams(_baseRate, _kink);
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
        _validateParams(_baseRate, _kink);
        baseRate = _baseRate;
        multiplier = _multiplier;
        jumpMultiplier = _jumpMultiplier;
        kink = _kink;
        emit RateParamsUpdated(_baseRate, _multiplier, _jumpMultiplier, _kink);
    }

    function getUtilization(uint256 totalBorrowed, uint256 totalDeposits) public pure returns (uint256) {
        if (totalDeposits == 0) return 0;
        if (totalBorrowed >= totalDeposits) return MAX_UTILIZATION;

        uint256 utilization = (totalBorrowed * PRECISION) / totalDeposits;
        return utilization > MAX_UTILIZATION ? MAX_UTILIZATION : utilization;
    }

    function getBorrowRate(uint256 totalBorrowed, uint256 totalDeposits) external view returns (uint256) {
        return _calculateBorrowRate(totalBorrowed, totalDeposits);
    }

    function getInterestRate(uint256 totalBorrowed, uint256 totalDeposits) external view returns (uint256) {
        return _calculateBorrowRate(totalBorrowed, totalDeposits);
    }

    function getSupplyRate(
        uint256 totalBorrowed,
        uint256 totalDeposits,
        uint256 reserveFactor
    ) external view returns (uint256) {
        uint256 utilization = getUtilization(totalBorrowed, totalDeposits);
        uint256 borrowRate = _calculateBorrowRate(totalBorrowed, totalDeposits);
        uint256 rateToPool = (borrowRate * (PRECISION - reserveFactor)) / PRECISION;
        return (utilization * rateToPool) / PRECISION;
    }

    function getAnnualRate(uint256 totalBorrowed, uint256 totalDeposits) external view returns (uint256) {
        return _calculateBorrowRate(totalBorrowed, totalDeposits) * BLOCKS_PER_YEAR;
    }

    function _calculateBorrowRate(uint256 totalBorrowed, uint256 totalDeposits) internal view returns (uint256) {
        uint256 utilization = getUtilization(totalBorrowed, totalDeposits);

        if (utilization <= kink) {
            return baseRate + (utilization * multiplier) / PRECISION;
        }

        uint256 normalRate = baseRate + (kink * multiplier) / PRECISION;
        uint256 excessUtilization = utilization - kink;
        uint256 jumpRate = (excessUtilization * jumpMultiplier) / (PRECISION - kink);

        return normalRate + jumpRate;
    }

    function _validateParams(uint256 _baseRate, uint256 _kink) internal pure {
        require(_baseRate >= MIN_BASE_RATE && _baseRate <= MAX_BASE_RATE, "Base rate out of bounds");
        require(_kink > 0 && _kink < PRECISION, "Invalid kink");
    }
}
