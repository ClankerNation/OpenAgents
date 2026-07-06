// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// ─────────────────────────────────────────────────────────────
// Contributor Metadata
// ─────────────────────────────────────────────────────────────
// Agent: Hermes Agent (Nous Research)
// Runtime: Python 3.x, Linux 6.8.0-117-generic, x86_64
// Working Directory: /home/ubuntu/openagents-fix
// Shell: bash
// Platform: Telegram Gateway
// Session: KTL DAO / Thread #1252
// ─────────────────────────────────────────────────────────────

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @title SimpleSwap
/// @notice Single-pair token swap contract with slippage protection and deadline
/// @dev Fixed version — adds minAmountOut, deadline, and minimum 1 wei fee
contract SimpleSwap {
    IERC20 public immutable tokenA;
    IERC20 public immutable tokenB;

    uint256 public reserveA;
    uint256 public reserveB;

    uint256 public constant FEE_BPS = 30; // 0.3% = 30 basis points
    uint256 public constant BASIS_POINTS = 10000;

    event Swap(
        address indexed user,
        address tokenIn,
        uint256 amountIn,
        uint256 amountOut,
        uint256 fee
    );
    event LiquidityAdded(
        address indexed provider,
        uint256 amountA,
        uint256 amountB
    );

    constructor(address _tokenA, address _tokenB) {
        require(_tokenA != address(0) && _tokenB != address(0), "Zero address");
        require(_tokenA != _tokenB, "Identical tokens");
        tokenA = IERC20(_tokenA);
        tokenB = IERC20(_tokenB);
    }

    /// @notice Add liquidity to the pool
    /// @param amountA Amount of tokenA to deposit
    /// @param amountB Amount of tokenB to deposit
    function addLiquidity(uint256 amountA, uint256 amountB) external {
        require(amountA > 0 && amountB > 0, "Zero amounts");

        require(
            tokenA.transferFrom(msg.sender, address(this), amountA),
            "Transfer A failed"
        );
        require(
            tokenB.transferFrom(msg.sender, address(this), amountB),
            "Transfer B failed"
        );

        reserveA += amountA;
        reserveB += amountB;

        emit LiquidityAdded(msg.sender, amountA, amountB);
    }

    /// @notice Swap tokenIn for tokenOut with slippage protection and deadline
    /// @param tokenIn Address of input token
    /// @param amountIn Amount of input token to swap
    /// @param minAmountOut Minimum output tokens to receive (slippage protection)
    /// @param deadline Unix timestamp after which the swap reverts
    /// @return amountOut Amount of output tokens received
    function swap(
        address tokenIn,
        uint256 amountIn,
        uint256 minAmountOut,
        uint256 deadline
    ) external returns (uint256 amountOut) {
        // ── Validation ──────────────────────────────────────
        require(tokenIn == address(tokenA) || tokenIn == address(tokenB), "Invalid token");
        require(amountIn > 0, "Zero input");
        require(minAmountOut > 0, "Zero min output");
        // FIX: deadline check prevents stale transaction attacks
        require(block.timestamp <= deadline, "Expired");

        // ── Determine reserves ──────────────────────────────
        bool isA = tokenIn == address(tokenA);
        (uint256 resIn, uint256 resOut) = isA
            ? (reserveA, reserveB)
            : (reserveB, reserveA);

        require(resIn > 0 && resOut > 0, "No liquidity");

        // ── Calculate fee ───────────────────────────────────
        // FIX: minimum 1 wei fee for any swap, prevents fee truncation to zero
        // for small amounts (amountIn * 30 / 10000 = 0 when amountIn < 334)
        uint256 fee = (amountIn * FEE_BPS) / BASIS_POINTS;
        if (fee == 0) {
            fee = 1;
        }

        uint256 amountInAfterFee = amountIn - fee;

        // ── Constant product: (resIn + amountInAfterFee) * (resOut - amountOut) = resIn * resOut
        // ── amountOut = amountInAfterFee * resOut / (resIn + amountInAfterFee)
        amountOut = (amountInAfterFee * resOut) / (resIn + amountInAfterFee);

        // ── Slippage protection ─────────────────────────────
        // FIX: reverts if output below user's minimum, prevents sandwich attacks
        require(amountOut >= minAmountOut, "Slippage exceeded");

        // ── Execute transfers ───────────────────────────────
        IERC20 tIn = isA ? tokenA : tokenB;
        IERC20 tOut = isA ? tokenB : tokenA;

        require(
            tIn.transferFrom(msg.sender, address(this), amountIn),
            "Transfer in failed"
        );
        require(
            tOut.transfer(msg.sender, amountOut),
            "Transfer out failed"
        );

        // ── Update reserves ─────────────────────────────────
        if (isA) {
            reserveA += amountIn;
            reserveB -= amountOut;
        } else {
            reserveB += amountIn;
            reserveA -= amountOut;
        }

        emit Swap(msg.sender, tokenIn, amountIn, amountOut, fee);
    }

    /// @notice View current pool reserves
    function getReserves() external view returns (uint256, uint256) {
        return (reserveA, reserveB);
    }

    /// @notice Calculate expected output for a swap (read-only)
    /// @param tokenIn Input token address
    /// @param amountIn Input amount
    /// @return amountOut Expected output amount
    /// @return fee Fee that will be charged (minimum 1 wei)
    function getAmountOut(
        address tokenIn,
        uint256 amountIn
    ) external view returns (uint256 amountOut, uint256 fee) {
        require(tokenIn == address(tokenA) || tokenIn == address(tokenB), "Invalid token");
        require(amountIn > 0, "Zero input");

        bool isA = tokenIn == address(tokenA);
        (uint256 resIn, uint256 resOut) = isA
            ? (reserveA, reserveB)
            : (reserveB, reserveA);

        if (resIn == 0 || resOut == 0) return (0, 0);

        fee = (amountIn * FEE_BPS) / BASIS_POINTS;
        if (fee == 0) {
            fee = 1;
        }

        uint256 amountInAfterFee = amountIn - fee;
        amountOut = (amountInAfterFee * resOut) / (resIn + amountInAfterFee);
    }
}
