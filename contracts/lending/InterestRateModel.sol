// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract InterestRateModel {
    uint256 public baseRate = 2e16;  // 2%
    uint256 public slope = 1e17;     // 10%
    uint256 public currentRate;
    
    event InterestRateUpdated(uint256 oldRate, uint256 newRate, uint256 timestamp);  // Fix #193
    event UtilizationUpdated(uint256 utilization, uint256 timestamp);  // Fix #193
    event BorrowRateUpdated(uint256 borrowRate);  // Fix #193
    
    function updateInterestRate(uint256 _newRate) external {
        uint256 oldRate = currentRate;
        currentRate = _newRate;
        emit InterestRateUpdated(oldRate, _newRate, block.timestamp);  // Fix #193
    }
    
    function calculateBorrowRate(uint256 utilization) external returns (uint256) {
        uint256 rate = baseRate + (utilization * slope / 1e18);
        emit UtilizationUpdated(utilization, block.timestamp);  // Fix #193
        emit BorrowRateUpdated(rate);  // Fix #193
        return rate;
    }
}
