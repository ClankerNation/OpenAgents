// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title InterestRateModel
/// @notice Variable interest rate model based on pool utilization with event emission and parameter getter
/// @dev Rate increases with utilization, with a kink at the optimal point.
///      All parameter changes emit events with old and new values for off-chain monitoring.
contract InterestRateModel {
    uint256 public baseRate;
    uint256 public multiplier;
    uint256 public jumpMultiplier;
    uint256 public kink; // optimal utilization (e.g., 80% = 0.8e18)

    uint256 public constant PRECISION = 1e18;
    uint256 public constant BLOCKS_PER_YEAR = 2_628_000; // ~12s blocks

    address public admin;

    /// @notice Emitted when rate parameters are updated. Includes both old and new values.
    /// @param oldBaseRate Previous base rate value
    /// @param newBaseRate New base rate value
    /// @param oldMultiplier Previous multiplier value
    /// @param newMultiplier New multiplier value
    /// @param oldJumpMultiplier Previous jump multiplier value
    /// @param newJumpMultiplier New jump multiplier value
    /// @param oldKink Previous kink value
    /// @param newKink New kink value
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

    /// @notice Update all rate parameters. Emits event with old and new values.
    /// @param _baseRate New base rate per block
    /// @param _multiplier New slope multiplier below kink
    /// @param _jumpMultiplier New slope multiplier above kink
    /// @param _kink New optimal utilization threshold
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

    /// @notice Returns all current rate parameters in a single call.
    /// @return params Struct containing baseRate, multiplier, jumpMultiplier, and kink
    struct Parameters {
        uint256 baseRate;
        uint256 multiplier;
        uint256 jumpMultiplier;
        uint256 kink;
    }

    function getParameters() external view returns (Parameters memory params) {
        return Parameters({
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

    function getBorrowRate(uint256 totalBorrowed, uint256 totalDeposits) external view returns (uint256) {
        uint256 utilization = getUtilization(totalBorrowed, totalDeposits);

        if (utilization <= kink) {
            return baseRate + (utilization * multiplier) / PRECISION;
        }

        uint256 normalRate = baseRate + (kink * multiplier) / PRECISION;
        uint256 excessUtilization = utilization - kink;
        uint256 denominator = PRECISION - kink;
        // Prevent division by zero when kink == PRECISION
        if (denominator == 0) {
            return normalRate;
        }
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
