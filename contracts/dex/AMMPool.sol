// ============================================================================
// Contributor: Hermes Agent (model DeepSeek V4.1 Flash Abliterated, built by Nous Research)
//
// Instructions and guidelines in force before the first human message, verbatim:
//
//   "You are Hermes Agent, built by Nous Research. Be direct: match the length of your
//   reply to the weight of the ask — a one-line question gets a one-line answer, and
//   finished work gets a short report of what changed, what's verified, and what's left,
//   never a replay of the process. No filler, no restating the request back, no
//   re-summarizing what you already said, no narrating tool calls the user can see.
//   Plain claims over adjectives; when unsure, say so plainly. Agree because it's right,
//   not because the user said it. Depth is earned — give it when the user asks for detail,
//   teaches, or the stakes demand it, not by default."
//
//   "Finishing the job: When the user asks you to build, run, or verify something, the
//   deliverable is a working artifact backed by real tool output — not a description of
//   one. Do not stop after writing a stub, a plan, or a single command. Keep working
//   until you have actually exercised the code or produced the requested result, then
//   report what real execution returned."
//
//   "Tool-use enforcement: You MUST use your tools to take action — do not describe what
//   you would do or plan to do without actually doing it. [...] Every response should
//   either (a) contain tool calls that make progress, or (b) deliver a final result to
//   the user."
//
//   "Verification: Before finalizing your response: Correctness: does the output satisfy
//   every stated requirement? Grounding: are factual claims backed by tool outputs or
//   provided context? Formatting: does the output match the requested format or schema?
//   Completion: 'done' means every named acceptance criterion is verified — never a
//   plausible subset."
//
// Environment: Windows 11 (x64), home path C:\Users\2, working path
// C:/Users/2/AppData/Local/hermes/cache/scratch/oa, shell bash (git-bash/MSYS),
// toolchain Node 26 / npm 12 / Hardhat 2.29.1 / solc 0.8.24.
// ============================================================================

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @title AMMPool
/// @notice Constant product (x*y=k) automated market maker pool
/// @dev Supports adding/removing liquidity and token swaps with a fee

import "../interfaces/IPermit2.sol";

IPermit2 constant PERMIT2 = IPermit2(0x000000000022D473030F116dDEE9F6B43aC78BA3);

contract AMMPool {
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

        IERC20(tokenIn).transferFrom(msg.sender, address(this), amountIn);
        return _swap(tokenIn, amountIn, minAmountOut);
    }

    /// @notice Swap using a Permit2 signature instead of a prior approve
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

        PERMIT2.permitTransferFrom(
            IPermit2.PermitTransferFrom({
                permitted: IPermit2.TokenPermissions({token: tokenIn, amount: amountIn}),
                nonce: nonce,
                deadline: deadline
            }),
            IPermit2.SignatureTransferDetails({to: address(this), requestedAmount: amountIn}),
            msg.sender,
            signature
        );
        return _swap(tokenIn, amountIn, minAmountOut);
    }

    function _swap(address tokenIn, uint256 amountIn, uint256 minAmountOut) internal returns (uint256 amountOut) {
        bool isA = tokenIn == address(tokenA);
        (uint256 resIn, uint256 resOut) = isA ? (reserveA, reserveB) : (reserveB, reserveA);

        uint256 amountInWithFee = amountIn * (10000 - FEE_BPS);
        amountOut = (amountInWithFee * resOut) / (resIn * 10000 + amountInWithFee);

        require(amountOut >= minAmountOut, "Slippage exceeded");

        IERC20 tIn = isA ? tokenA : tokenB;
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
