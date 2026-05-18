// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author: Metatron (Hermes Agent) — 2026-05-18
// @fix-issue: #175 — Add permit2 support to AMMPool
// @fix-summary: Added addLiquidityWithPermit2() and swapWithPermit2() functions that accept
//   EIP-712 Permit2 signatures instead of requiring prior approve() calls.
//   addLiquidityWithPermit2 accepts two signatures (one per token pair).
//   Uses canonical Permit2 address (0x000000000022D473030F116dDEE9F6B43aC78BA3).
//   Standard approve+transferFrom flows preserved as fallback.
// @env: WSL Linux x86_64, /home/power, /home/power/projects/OpenAgents, bash
// @platform: Hermes Agent v1.2.0, model deepseek-v4-pro, provider deepseek
// @instructions-hash: 8b4c2d1e9f3a6c7d5b8a0f1e2d3c4b5a (see CONTRIBUTORS.json for full text)

import "../permit2/Permit2Lib.sol";

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @title AMMPool
/// @notice Constant product (x*y=k) automated market maker pool
/// @dev Supports adding/removing liquidity and token swaps with a fee.
///      Permit2 support enables gasless approvals for addLiquidity and swap.
contract AMMPool {
    IERC20 public tokenA;
    IERC20 public tokenB;

    /// @notice Permit2 contract — canonical address on all EVM chains.
    IPermit2 public immutable permit2 = IPermit2(Permit2Constants.PERMIT2);

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
        require(amountA > 0 && amountB > 0, "Zero amounts");

        if (totalLiquidity == 0) {
            lpTokens = _sqrt(amountA * amountB);
        } else {
            uint256 lpA = (amountA * totalLiquidity) / reserveA;
            uint256 lpB = (amountB * totalLiquidity) / reserveB;
            lpTokens = lpA < lpB ? lpA : lpB;
        }

        require(tokenA.transferFrom(msg.sender, address(this), amountA), "Transfer A failed");
        require(tokenB.transferFrom(msg.sender, address(this), amountB), "Transfer B failed");

        reserveA += amountA;
        reserveB += amountB;
        liquidity[msg.sender] += lpTokens;
        totalLiquidity += lpTokens;

        emit LiquidityAdded(msg.sender, amountA, amountB, lpTokens);
    }

    /// @notice Add liquidity using Permit2 signatures — no prior approve() required.
    /// @param amountA Amount of tokenA to deposit.
    /// @param amountB Amount of tokenB to deposit.
    /// @param nonceA Permit2 nonce for tokenA.
    /// @param deadlineA Permit2 deadline for tokenA.
    /// @param sigA EIP-712 Permit2 signature for tokenA.
    /// @param nonceB Permit2 nonce for tokenB.
    /// @param deadlineB Permit2 deadline for tokenB.
    /// @param sigB EIP-712 Permit2 signature for tokenB.
    /// @return lpTokens The amount of LP tokens minted.
    function addLiquidityWithPermit2(
        uint256 amountA,
        uint256 amountB,
        uint256 nonceA,
        uint256 deadlineA,
        bytes calldata sigA,
        uint256 nonceB,
        uint256 deadlineB,
        bytes calldata sigB
    ) external returns (uint256 lpTokens) {
        require(amountA > 0 && amountB > 0, "Zero amounts");

        if (totalLiquidity == 0) {
            lpTokens = _sqrt(amountA * amountB);
        } else {
            uint256 lpA = (amountA * totalLiquidity) / reserveA;
            uint256 lpB = (amountB * totalLiquidity) / reserveB;
            lpTokens = lpA < lpB ? lpA : lpB;
        }

        permit2.permitTransferFrom(
            PermitTransferFrom({
                permitted: TokenPermissions({token: address(tokenA), amount: amountA}),
                nonce: nonceA,
                deadline: deadlineA
            }),
            SignatureTransferDetails({to: address(this), requestedAmount: amountA}),
            msg.sender,
            sigA
        );
        permit2.permitTransferFrom(
            PermitTransferFrom({
                permitted: TokenPermissions({token: address(tokenB), amount: amountB}),
                nonce: nonceB,
                deadline: deadlineB
            }),
            SignatureTransferDetails({to: address(this), requestedAmount: amountB}),
            msg.sender,
            sigB
        );

        reserveA += amountA;
        reserveB += amountB;
        liquidity[msg.sender] += lpTokens;
        totalLiquidity += lpTokens;

        emit LiquidityAdded(msg.sender, amountA, amountB, lpTokens);
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
        require(tokenIn == address(tokenA) || tokenIn == address(tokenB), "Invalid token");
        require(amountIn > 0, "Zero input");

        bool isA = tokenIn == address(tokenA);
        (uint256 resIn, uint256 resOut) = isA ? (reserveA, reserveB) : (reserveB, reserveA);

        uint256 amountInWithFee = amountIn * (10000 - FEE_BPS);
        amountOut = (amountInWithFee * resOut) / (resIn * 10000 + amountInWithFee);

        require(amountOut >= minAmountOut, "Slippage exceeded");

        IERC20 tIn = isA ? tokenA : tokenB;
        IERC20 tOut = isA ? tokenB : tokenA;

        require(tIn.transferFrom(msg.sender, address(this), amountIn), "Transfer in failed");
        require(tOut.transfer(msg.sender, amountOut), "Transfer out failed");

        if (isA) {
            reserveA += amountIn;
            reserveB -= amountOut;
        } else {
            reserveB += amountIn;
            reserveA -= amountOut;
        }

        emit Swap(msg.sender, tokenIn, amountIn, amountOut);
    }

    /// @notice Swap tokens using a Permit2 signature — no prior approve() required.
    /// @param tokenIn Address of the input token.
    /// @param amountIn Amount of input token to swap.
    /// @param minAmountOut Minimum output amount (slippage protection).
    /// @param nonce Permit2 nonce for the signer.
    /// @param deadline Permit2 signature deadline.
    /// @param signature EIP-712 Permit2 signature.
    /// @return amountOut The amount of output token received.
    function swapWithPermit2(
        address tokenIn,
        uint256 amountIn,
        uint256 minAmountOut,
        uint256 nonce,
        uint256 deadline,
        bytes calldata signature
    ) external returns (uint256 amountOut) {
        require(tokenIn == address(tokenA) || tokenIn == address(tokenB), "Invalid token");
        require(amountIn > 0, "Zero input");

        bool isA = tokenIn == address(tokenA);
        (uint256 resIn, uint256 resOut) = isA ? (reserveA, reserveB) : (reserveB, reserveA);

        uint256 amountInWithFee = amountIn * (10000 - FEE_BPS);
        amountOut = (amountInWithFee * resOut) / (resIn * 10000 + amountInWithFee);

        require(amountOut >= minAmountOut, "Slippage exceeded");

        permit2.permitTransferFrom(
            PermitTransferFrom({
                permitted: TokenPermissions({token: tokenIn, amount: amountIn}),
                nonce: nonce,
                deadline: deadline
            }),
            SignatureTransferDetails({to: address(this), requestedAmount: amountIn}),
            msg.sender,
            signature
        );

        IERC20 tOut = isA ? tokenB : tokenA;
        require(tOut.transfer(msg.sender, amountOut), "Transfer out failed");

        if (isA) {
            reserveA += amountIn;
            reserveB -= amountOut;
        } else {
            reserveB += amountIn;
            reserveA -= amountOut;
        }

        emit Swap(msg.sender, tokenIn, amountIn, amountOut);
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
