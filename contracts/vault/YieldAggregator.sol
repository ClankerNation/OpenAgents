// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract YieldAggregator {
    IERC20 public token;
    address[] public strategies;
    mapping(address => uint256) public strategyAllocations;  // Fix #134
    mapping(address => uint256) public strategyYields;  // Fix #134
    
    event StrategyAdded(address indexed strategy, uint256 allocation);
    event YieldUpdated(address indexed strategy, uint256 yield);
    
    constructor(address _token) { token = IERC20(_token); }
    
    function addStrategy(address strategy, uint256 allocation) external {
        strategies.push(strategy);
        strategyAllocations[strategy] = allocation;
        emit StrategyAdded(strategy, allocation);
    }
    
    function updateYield(address strategy, uint256 yield) external {
        strategyYields[strategy] = yield;
        emit YieldUpdated(strategy, yield);
    }
    
    function getTotalYield() external view returns (uint256) {
        uint256 total = 0;
        for (uint i = 0; i < strategies.length; i++) {
            total += strategyYields[strategies[i]];
        }
        return total;
    }
}
