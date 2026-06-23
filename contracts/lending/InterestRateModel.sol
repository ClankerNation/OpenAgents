// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title InterestRateModel
/// @notice Variable interest rate model based on pool utilization
/// @dev Rate increases with utilization, with a kink at the optimal point
/// @contributor Gaotax2006
/// @platform Claude Code
/// @runtime Windows 11 Home China, x86_64, F:\\ai-bounty-work\\bounty-hunter
/// @date 2026-06-24T00:00:00Z
contract InterestRateModel {
    uint256 public baseRate;
    uint256 public multiplier;
    uint256 public jumpMultiplier;
    uint256 public kink;

    uint256 public constant PRECISION = 1e18;
    uint256 public constant BLOCKS_PER_YEAR = 2_628_000;

    address public admin;

    event RateParamsUpdated(uint256 baseRate, uint256 multiplier, uint256 jumpMultiplier, uint256 kink);
    
    event RateParametersUpdated(
        uint256 indexed oldBaseRate,
        uint256 indexed oldMultiplier,
        uint256 oldJumpMultiplier,
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
        uint256 oldBaseRate = baseRate;
        uint256 oldMultiplier = multiplier;
        uint256 oldJumpMultiplier = jumpMultiplier;
        uint256 oldKink = kink;

        baseRate = _baseRate;
        multiplier = _multiplier;
        jumpMultiplier = _jumpMultiplier;
        kink = _kink;

        emit RateParamsUpdated(_baseRate, _multiplier, _jumpMultiplier, _kink);
        emit RateParametersUpdated(
            oldBaseRate, oldMultiplier, oldJumpMultiplier, oldKink,
            _baseRate, _multiplier, _jumpMultiplier, _kink
        );
    }

    function getParameters() external view returns (
        uint256 _baseRate,
        uint256 _multiplier,
        uint256 _jumpMultiplier,
        uint256 _kinkOut
    ) {
        return (baseRate, multiplier, jumpMultiplier, kink);
    }

    function calculateRate(uint256 utilization) public view returns (uint256) {
        require(utilization <= PRECISION, "Utilization > 100%");
        if (utilization <= kink) {
            return (baseRate + (multiplier * utilization) / PRECISION);
        } else {
            uint256 normalRate = (baseRate + (multiplier * kink) / PRECISION);
            uint256 excessUtilization = utilization - kink;
            return normalRate + ((jumpMultiplier * excessUtilization) / PRECISION);
        }
    }
}
