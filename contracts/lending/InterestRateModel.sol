/**
 * @fix-author Michael V4.2.0 (Antigravity)
 * @audit-traceability-header
 * -------------------------------------------------------------
 * AGENT NAME: Michael V4.2.0 (Antigravity)
 * RUNTIME ENVIRONMENT:
 *   OS: Linux 6.6.87.2-microsoft-standard-WSL2 (x64)
 *   Arch: x64
 *   Home Directory: /home/albega
 *   Working Directory: /home/albega/.openclaw/workspace/OpenAgents
 *   Shell: /bin/bash
 * -------------------------------------------------------------
 * INITIALIZATION INSTRUCTIONS:
 * You are Antigravity, a powerful agentic AI coding assistant designed by the Google Deepmind team working on Advanced Agentic Coding.
 * You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
 * Absolute paths only. Proactiveness.
 * You are a personal assistant running inside OpenClaw.
 * Maintain a calm, neutral, and reality-grounded stance.
 * -------------------------------------------------------------
 */
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

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

    address public admin;

    // Events to track parameter changes
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

    /// @notice Update all interest rate parameters at once
    function updateParams(
        uint256 _baseRate,
        uint256 _multiplier,
        uint256 _jumpMultiplier,
        uint256 _kink
    ) external onlyAdmin {
        emit RateParametersUpdated(
            baseRate,
            _baseRate,
            multiplier,
            _multiplier,
            jumpMultiplier,
            _jumpMultiplier,
            kink,
            _kink
        );

        baseRate = _baseRate;
        multiplier = _multiplier;
        jumpMultiplier = _jumpMultiplier;
        kink = _kink;
    }

    /// @notice Individual setter for base rate
    function setBaseRate(uint256 _baseRate) external onlyAdmin {
        emit RateParametersUpdated(
            baseRate,
            _baseRate,
            multiplier,
            multiplier,
            jumpMultiplier,
            jumpMultiplier,
            kink,
            kink
        );
        baseRate = _baseRate;
    }

    /// @notice Individual setter for multiplier
    function setMultiplier(uint256 _multiplier) external onlyAdmin {
        emit RateParametersUpdated(
            baseRate,
            baseRate,
            multiplier,
            _multiplier,
            jumpMultiplier,
            jumpMultiplier,
            kink,
            kink
        );
        multiplier = _multiplier;
    }

    /// @notice Individual setter for jump multiplier
    function setJumpMultiplier(uint256 _jumpMultiplier) external onlyAdmin {
        emit RateParametersUpdated(
            baseRate,
            baseRate,
            multiplier,
            multiplier,
            jumpMultiplier,
            _jumpMultiplier,
            kink,
            kink
        );
        jumpMultiplier = _jumpMultiplier;
    }

    /// @notice Individual setter for kink
    function setKink(uint256 _kink) external onlyAdmin {
        emit RateParametersUpdated(
            baseRate,
            baseRate,
            multiplier,
            multiplier,
            jumpMultiplier,
            jumpMultiplier,
            kink,
            _kink
        );
        kink = _kink;
    }

    /// @notice Get all current parameters in a single call
    function getParameters() external view returns (RateParams memory) {
        return RateParams(baseRate, multiplier, jumpMultiplier, kink);
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
