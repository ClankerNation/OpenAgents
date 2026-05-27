// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../interfaces/IPermit2.sol";

// Contributor: Codex for charlie12520.
// Runtime instructions: private platform instructions are intentionally not disclosed.
// Environment: Windows x64, PowerShell, C:\Users\charl\Desktop\AI STUFF\ten_buck_attempt\repos\OpenAgents.

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @title AMMPool
/// @notice Constant product (x*y=k) automated market maker pool
/// @dev Supports adding/removing liquidity and token swaps with a fee
contract AMMPool {
    // Uniswap Permit2 is deployed at this deterministic address on supported chains.
    IPermit2 public constant PERMIT2 = IPermit2(0x000000000022D473030F116dDEE9F6B43aC78BA3);

    IERC20 public tokenA;
    IERC20 public tokenB;

    uint256 public reserveA;
    uint256 public reserveB;
    uint256 public totalLiquidity;
    uint256 public constant FEE_BPS = 30; // 0.3%

    mapping(address => uint256) public liquidity;

    event LiquidityAdded(address indexed provider, uint256 amountA, uint256 amountB, uint256 lpTokens);
    event LiquidityRemoved(address indexed provider, uint256 amountA, uint256 amountB);
    event Swap(address indexed user, address tokenIn, uint256 amountIn, uint256 amountOut);

    constructor(address _tokenA, address _tokenB) {
        tokenA = IERC20(_tokenA);
        tokenB = IERC20(_tokenB);
    }

    // BUG: No minimum liquidity lock — first LP can add tiny liquidity then remove it all,
    // enabling a well-known inflation attack where attacker donates tokens to manipulate
    // share price and steal from the next depositor
    function addLiquidity(uint256 amountA, uint256 amountB) external returns (uint256 lpTokens) {
        lpTokens = _calculateLiquidity(amountA, amountB);

        require(tokenA.transferFrom(msg.sender, address(this), amountA), "Transfer A failed");
        require(tokenB.transferFrom(msg.sender, address(this), amountB), "Transfer B failed");

        _recordLiquidity(amountA, amountB, lpTokens);
    }

    function addLiquidityWithPermit2(
        uint256 amountA,
        uint256 amountB,
        IPermit2.PermitTransferFrom calldata permitA,
        bytes calldata signatureA,
        IPermit2.PermitTransferFrom calldata permitB,
        bytes calldata signatureB
    ) external returns (uint256 lpTokens) {
        lpTokens = _calculateLiquidity(amountA, amountB);

        _pullWithPermit2(tokenA, amountA, permitA, signatureA);
        _pullWithPermit2(tokenB, amountB, permitB, signatureB);

        _recordLiquidity(amountA, amountB, lpTokens);
    }

    function removeLiquidity(uint256 lpTokens) external {
        require(lpTokens > 0 && lpTokens <= liquidity[msg.sender], "Invalid amount");

        uint256 amountA = (lpTokens * reserveA) / totalLiquidity;
        uint256 amountB = (lpTokens * reserveB) / totalLiquidity;

        liquidity[msg.sender] -= lpTokens;
        totalLiquidity -= lpTokens;
        reserveA -= amountA;
        reserveB -= amountB;

        require(tokenA.transfer(msg.sender, amountA), "Transfer A failed");
        require(tokenB.transfer(msg.sender, amountB), "Transfer B failed");

        emit LiquidityRemoved(msg.sender, amountA, amountB);
    }

    // BUG: Swap has no deadline parameter — transaction can sit in mempool and execute
    // at a much later time when price has moved unfavorably (stale transaction attack)
    // BUG: Fee truncates to zero for small swaps — (amountIn * 30) / 10000 rounds to 0
    // when amountIn < 334, meaning tiny swaps pay no fee and can drain value over time
    function swap(address tokenIn, uint256 amountIn, uint256 minAmountOut) external returns (uint256 amountOut) {
        (bool isA, IERC20 tIn, IERC20 tOut, uint256 quotedOut) = _quoteSwap(tokenIn, amountIn, minAmountOut);
        amountOut = quotedOut;

        require(tIn.transferFrom(msg.sender, address(this), amountIn), "Transfer in failed");
        require(tOut.transfer(msg.sender, amountOut), "Transfer out failed");

        _recordSwap(isA, tokenIn, amountIn, amountOut);
    }

    function swapWithPermit2(
        address tokenIn,
        uint256 amountIn,
        uint256 minAmountOut,
        IPermit2.PermitTransferFrom calldata permit,
        bytes calldata signature
    ) external returns (uint256 amountOut) {
        (bool isA, IERC20 tIn, IERC20 tOut, uint256 quotedOut) = _quoteSwap(tokenIn, amountIn, minAmountOut);
        amountOut = quotedOut;

        _pullWithPermit2(tIn, amountIn, permit, signature);
        require(tOut.transfer(msg.sender, amountOut), "Transfer out failed");

        _recordSwap(isA, tokenIn, amountIn, amountOut);
    }

    function _calculateLiquidity(uint256 amountA, uint256 amountB) internal view returns (uint256 lpTokens) {
        require(amountA > 0 && amountB > 0, "Zero amounts");

        if (totalLiquidity == 0) {
            lpTokens = _sqrt(amountA * amountB);
        } else {
            uint256 lpA = (amountA * totalLiquidity) / reserveA;
            uint256 lpB = (amountB * totalLiquidity) / reserveB;
            lpTokens = lpA < lpB ? lpA : lpB;
        }
    }

    function _recordLiquidity(uint256 amountA, uint256 amountB, uint256 lpTokens) internal {
        reserveA += amountA;
        reserveB += amountB;
        liquidity[msg.sender] += lpTokens;
        totalLiquidity += lpTokens;

        emit LiquidityAdded(msg.sender, amountA, amountB, lpTokens);
    }

    function _quoteSwap(
        address tokenIn,
        uint256 amountIn,
        uint256 minAmountOut
    ) internal view returns (bool isA, IERC20 tIn, IERC20 tOut, uint256 amountOut) {
        require(tokenIn == address(tokenA) || tokenIn == address(tokenB), "Invalid token");
        require(amountIn > 0, "Zero input");

        isA = tokenIn == address(tokenA);
        (uint256 resIn, uint256 resOut) = isA ? (reserveA, reserveB) : (reserveB, reserveA);

        uint256 amountInWithFee = amountIn * (10000 - FEE_BPS);
        amountOut = (amountInWithFee * resOut) / (resIn * 10000 + amountInWithFee);

        require(amountOut >= minAmountOut, "Slippage exceeded");

        tIn = isA ? tokenA : tokenB;
        tOut = isA ? tokenB : tokenA;
    }

    function _recordSwap(bool isA, address tokenIn, uint256 amountIn, uint256 amountOut) internal {
        if (isA) {
            reserveA += amountIn;
            reserveB -= amountOut;
        } else {
            reserveB += amountIn;
            reserveA -= amountOut;
        }

        emit Swap(msg.sender, tokenIn, amountIn, amountOut);
    }

    function _pullWithPermit2(
        IERC20 token,
        uint256 amount,
        IPermit2.PermitTransferFrom calldata permit,
        bytes calldata signature
    ) internal {
        // Bind the signed permission to the token and amount this function is about
        // to pull so a signature for another token or smaller amount cannot be reused.
        require(permit.permitted.token == address(token), "Permit token mismatch");
        require(permit.permitted.amount >= amount, "Permit amount too low");
        PERMIT2.permitTransferFrom(
            permit,
            IPermit2.SignatureTransferDetails({
                to: address(this),
                requestedAmount: amount
            }),
            msg.sender,
            signature
        );
    }

    function _sqrt(uint256 y) internal pure returns (uint256 z) {
        if (y > 3) {
            z = y;
            uint256 x = y / 2 + 1;
            while (x < z) { z = x; x = (y / x + x) / 2; }
        } else if (y != 0) {
            z = 1;
        }
    }

    function getReserves() external view returns (uint256, uint256) {
        return (reserveA, reserveB);
    }
}
