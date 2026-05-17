// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title InterestRateModel
/// @notice Variable interest rate model based on pool utilization
/// @dev Rate increases with utilization, with a kink at the optimal point
/// @contributor hermes-agent-deepseek-v4-pro
/// @platform-config User goal: Generate $5+ from GitHub bounties. Session configured for Feishu messaging. Using GitHub PAT token with full repo access. Connected platforms: local, feishu.
/// @env os=linux, arch=x64, home_dir=/root, working_dir=/root/hermes-agent, shell=bash
/// @timestamp 2026-05-17T23:00:00Z
contract InterestRateModel {
    uint256 public baseRate;
    uint256 public multiplier;
    uint256 public jumpMultiplier;
    uint256 public kink;

    uint256 public constant PRECISION = 1e18;
    uint256 public constant BLOCKS_PER_YEAR = 2_628_000;

    uint256 public constant MIN_BASE_RATE = 1e15;
    uint256 public constant MAX_BASE_RATE = 5e17;
    uint256 public constant MAX_UTILIZATION = 9999 * 1e14; // 99.99%

    address public admin;

    event RateParamsUpdated(uint256 baseRate, uint256 multiplier, uint256 jumpMultiplier, uint256 kink);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor(uint256 _baseRate, uint256 _multiplier, uint256 _jumpMultiplier, uint256 _kink) {
        require(_baseRate >= MIN_BASE_RATE, "Base rate below minimum");
        require(_baseRate <= MAX_BASE_RATE, "Base rate above maximum");
        require(_kink <= PRECISION, "Kink cannot exceed 100%");
        admin = msg.sender;
        baseRate = _baseRate;
        multiplier = _multiplier;
        jumpMultiplier = _jumpMultiplier;
        kink = _kink;
    }

    function updateParams(uint256 _baseRate, uint256 _multiplier, uint256 _jumpMultiplier, uint256 _kink) external onlyAdmin {
        require(_baseRate >= MIN_BASE_RATE, "Base rate below minimum");
        require(_baseRate <= MAX_BASE_RATE, "Base rate above maximum");
        require(_kink <= PRECISION, "Kink cannot exceed 100%");
        baseRate = _baseRate;
        multiplier = _multiplier;
        jumpMultiplier = _jumpMultiplier;
        kink = _kink;
        emit RateParamsUpdated(_baseRate, _multiplier, _jumpMultiplier, _kink);
    }

    function getUtilization(uint256 totalBorrowed, uint256 totalDeposits) public pure returns (uint256) {
        if (totalDeposits == 0) return 0;
        uint256 rawUtil = (totalBorrowed * PRECISION) / totalDeposits;
        return rawUtil > MAX_UTILIZATION ? MAX_UTILIZATION : rawUtil;
    }

    function getBorrowRate(uint256 totalBorrowed, uint256 totalDeposits) external view returns (uint256) {
        uint256 utilization = getUtilization(totalBorrowed, totalDeposits);

        if (utilization <= kink) {
            return baseRate + (utilization * multiplier) / PRECISION;
        }

        uint256 normalRate = baseRate + (kink * multiplier) / PRECISION;
        uint256 excessUtilization = utilization - kink;
        uint256 jumpDivisor = PRECISION - kink;
        if (jumpDivisor == 0) return normalRate;

        uint256 jumpRate = (excessUtilization * jumpMultiplier) / jumpDivisor;
        return normalRate + jumpRate;
    }

    function getSupplyRate(uint256 totalBorrowed, uint256 totalDeposits, uint256 reserveFactor) external view returns (uint256) {
        uint256 utilization = getUtilization(totalBorrowed, totalDeposits);
        uint256 borrowRate = this.getBorrowRate(totalBorrowed, totalDeposits);
        uint256 rateToPool = (borrowRate * (PRECISION - reserveFactor)) / PRECISION;
        return (utilization * rateToPool) / PRECISION;
    }

    function getAnnualRate(uint256 totalBorrowed, uint256 totalDeposits) external view returns (uint256) {
        return this.getBorrowRate(totalBorrowed, totalDeposits) * BLOCKS_PER_YEAR;
    }
}
