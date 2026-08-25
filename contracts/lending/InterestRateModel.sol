// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
// @fix-author rafaio1
// @date 2026-08-25T02:25:00Z
// @runtime linux x64 /tmp/openagents_issue_202 bash
// @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement, senior dev multi-agent orchestration, and Wise payout integration.

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

    event RateParamsUpdated(
        uint256 oldBaseRate, uint256 newBaseRate,
        uint256 oldMultiplier, uint256 newMultiplier,
        uint256 oldJumpMultiplier, uint256 newJumpMultiplier,
        uint256 oldKink, uint256 newKink
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

    struct RateParameters {
        uint256 baseRate;
        uint256 multiplier;
        uint256 jumpMultiplier;
        uint256 kink;
    }

    /// @notice Returns all current rate parameters in a single call.
    function getParameters() external view returns (RateParameters memory) {
        return RateParameters(baseRate, multiplier, jumpMultiplier, kink);
    }

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

        emit RateParamsUpdated(
            oldBaseRate, _baseRate,
            oldMultiplier, _multiplier,
            oldJumpMultiplier, _jumpMultiplier,
            oldKink, _kink
        );
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
