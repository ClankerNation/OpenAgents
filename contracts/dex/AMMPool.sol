// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract AMMPool {
    IERC20 public tokenA;
    IERC20 public tokenB;
    uint256 public reserveA;
    uint256 public reserveB;
    
    event Swap(address indexed sender, address indexed recipient, uint256 amountAIn, uint256 amountBOut, uint256 timestamp);  // Fix #165
    event LiquidityAdded(address indexed provider, uint256 amountA, uint256 amountB, uint256 timestamp);  // Fix #165
    event LiquidityRemoved(address indexed provider, uint256 amountA, uint256 amountB);  // Fix #165
    
    constructor(address _a, address _b) { tokenA = IERC20(_a); tokenB = IERC20(_b); }
    
    function swap(uint256 amountIn, bool isAtoB) external {
        if (isAtoB) {
            tokenA.transferFrom(msg.sender, address(this), amountIn);
            uint256 out = getAmountOut(amountIn, reserveA, reserveB);
            tokenB.transfer(msg.sender, out);
            reserveA += amountIn;
            reserveB -= out;
            emit Swap(msg.sender, msg.sender, amountIn, out, block.timestamp);
        } else {
            tokenB.transferFrom(msg.sender, address(this), amountIn);
            uint256 out = getAmountOut(amountIn, reserveB, reserveA);
            tokenA.transfer(msg.sender, out);
            reserveB += amountIn;
            reserveA -= out;
            emit Swap(msg.sender, msg.sender, out, amountIn, block.timestamp);
        }
    }
    
    function getAmountOut(uint256 amountIn, uint256 reserveIn, uint256 reserveOut) public pure returns (uint256) {
        return (amountIn * 997 * reserveOut) / (reserveIn * 1000 + amountIn * 997);
    }
}
