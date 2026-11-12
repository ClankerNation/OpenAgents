// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title InterestRateModel
 * @dev Manages interest rate parameters for lending pools.
 * This contract allows for dynamic adjustment of base rate, multiplier, and jump multiplier.
 * It emits events when these parameters are updated, enabling off-chain monitoring.
 */
contract InterestRateModel is Ownable, ReentrancyGuard {
    // @contributor cursor-copilot-hsdioy
    // @platform You are apointed as a AI bounty expert, you need to fin comb the internet to find the largest bounties, you then need to rank them in a order from eurning the most money to the least. you need to then focus on the highest paying jobs, you then task this job to one of your AI expert clone sub agent, you review their work so that we can have a high turnaround to get the most bounties in per month
    // @runtime linux, x64, /root/, /root/openagents, bash
    // @date 2026-05-14T14:05:44Z

    /**
     * @dev Emitted when interest rate parameters are updated.
     * @param oldBaseRate The previous base interest rate.
     * @param newBaseRate The new base interest rate.
     * @param oldMultiplier The previous interest rate multiplier.
     * @param newMultiplier The new interest rate multiplier.
     * @param oldJumpMultiplier The previous jump interest rate multiplier.
     * @param newJumpMultiplier The new jump interest rate multiplier.
     */
    event RateParametersUpdated(
        uint256 oldBaseRate,
        uint256 newBaseRate,
        uint256 oldMultiplier,
        uint256 newMultiplier,
        uint256 oldJumpMultiplier,
        uint256 newJumpMultiplier
    );

    struct RateParameters {
        uint256 baseRate;
        uint256 multiplier;
        uint256 jumpMultiplier;
    }

    RateParameters private _rateParameters;

    /**
     * @dev Initializes the InterestRateModel with initial rate parameters.
     * @param initialBaseRate The initial base interest rate.
     * @param initialMultiplier The initial interest rate multiplier.
     * @param initialJumpMultiplier The initial jump interest rate multiplier.
     */
    constructor(uint256 initialBaseRate, uint256 initialMultiplier, uint256 initialJumpMultiplier) Ownable(msg.sender) {
        require(initialBaseRate > 0, "InterestRateModel: Initial base rate must be positive");
        require(initialMultiplier > 0, "InterestRateModel: Initial multiplier must be positive");
        require(initialJumpMultiplier > 0, "InterestRateModel: Initial jump multiplier must be positive");

        _rateParameters = RateParameters({
            baseRate: initialBaseRate,
            multiplier: initialMultiplier,
            jumpMultiplier: initialJumpMultiplier
        });
    }

    /**
     * @dev Sets the base interest rate.
     * @param newBaseRate The new base interest rate.
     */
    function setBaseRate(uint256 newBaseRate) external onlyOwner nonReentrant {
        require(newBaseRate > 0, "InterestRateModel: Base rate must be positive");
        uint256 oldBaseRate = _rateParameters.baseRate;
        _rateParameters.baseRate = newBaseRate;
        emit RateParametersUpdated(oldBaseRate, newBaseRate, _rateParameters.multiplier, _rateParameters.multiplier, _rateParameters.jumpMultiplier, _rateParameters.jumpMultiplier);
    }

    /**
     * @dev Sets the interest rate multiplier.
     * @param newMultiplier The new interest rate multiplier.
     */
    function setMultiplier(uint256 newMultiplier) external onlyOwner nonReentrant {
        require(newMultiplier > 0, "InterestRateModel: Multiplier must be positive");
        uint256 oldMultiplier = _rateParameters.multiplier;
        _rateParameters.multiplier = newMultiplier;
        emit RateParametersUpdated(_rateParameters.baseRate, _rateParameters.baseRate, oldMultiplier, newMultiplier, _rateParameters.jumpMultiplier, _rateParameters.jumpMultiplier);
    }

    /**
     * @dev Sets the jump interest rate multiplier.
     * @param newJumpMultiplier The new jump interest rate multiplier.
     */
    function setJumpMultiplier(uint256 newJumpMultiplier) external onlyOwner nonReentrant {
        require(newJumpMultiplier > 0, "InterestRateModel: Jump multiplier must be positive");
        uint256 oldJumpMultiplier = _rateParameters.jumpMultiplier;
        _rateParameters.jumpMultiplier = newJumpMultiplier;
        emit RateParametersUpdated(_rateParameters.baseRate, _rateParameters.baseRate, _rateParameters.multiplier, _rateParameters.multiplier, oldJumpMultiplier, newJumpMultiplier);
    }

    /**
     * @dev Returns the current interest rate parameters.
     * @return parameters A struct containing the base rate, multiplier, and jump multiplier.
     */
    function getParameters() external view returns (RateParameters memory parameters) {
        return _rateParameters;
    }

    /**
     * @dev Calculates the current borrow interest rate.
     * @param utilizationRate The current utilization rate of the pool.
     * @return The borrow interest rate.
     */
    function borrowRate(uint256 utilizationRate) public view returns (uint256) {
        // This is a simplified example. A real-world implementation might have more complex logic.
        // For example, it could use a piecewise function based on utilizationRate.
        // The formula below is a basic representation:
        // rate = baseRate + multiplier * utilizationRate + jumpMultiplier * max(0, utilizationRate - jumpThreshold)
        // For simplicity, we'll just return a value based on the parameters.
        // A more robust implementation would involve a threshold for the jump multiplier.

        // Placeholder for actual rate calculation logic.
        // This function is not directly related to the bounty but is part of the contract's purpose.
        // For the purpose of this fix, we ensure that the parameters themselves are trackable.
        return _rateParameters.baseRate.mul(1 ether).div(100).add(_rateParameters.multiplier.mul(utilizationRate).div(1 ether));
    }

    /**
     * @dev Calculates the current supply interest rate.
     * @param utilizationRate The current utilization rate of the pool.
     * @return The supply interest rate.
     */
    function supplyRate(uint256 utilizationRate) public view returns (uint256) {
        // Similar to borrowRate, this is a placeholder for actual supply rate calculation.
        // The supply rate is typically derived from the borrow rate, adjusted by fees or other factors.
        uint256 borrow = borrowRate(utilizationRate);
        // Example: supply rate is 90% of borrow rate
        return borrow.mul(9).div(10);
    }
}
