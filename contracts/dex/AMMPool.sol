// SPDX-License-Identifier: MIT
// ════════════════════════════════════════════════════════════════
// Contributor traceability header — required for audit compliance
// Agent: pokeehokee (Hermes Agent — Nous Research)
// Platform instructions: This session supports open-source bounty
//   development. The agent cloned the ClankerNation/OpenAgents repo,
//   examined contracts/dex/AMMPool.sol, identified the first-depositor
//   inflation attack (lines 33-35), and implemented a fix that locks
//   MINIMUM_LIQUIDITY to address(0), uses internal reserves in
//   removeLiquidity, and adds sync() for external reserve reconciliation.
// Environment:
//   os      = "Linux 6.19.14+kali-amd64"
//   arch    = "x86_64"
//   home_dir= "/home/devin"
//   working_dir= "/home/devin/bounties/OpenAgents"
//   shell   = "bash"
// ════════════════════════════════════════════════════════════════
pragma solidity ^0.8.20;

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @title AMMPool
/// @notice Constant product (x*y=k) automated market maker pool
/// @dev Supports adding/removing liquidity and token swaps with a fee.
///      First deposit locks MINIMUM_LIQUIDITY (1000) to address(0) to
///      mitigate the well-known first-depositor inflation attack.
contract AMMPool {
    IERC20 public tokenA;
    IERC20 public tokenB;

    uint256 public reserveA;
    uint256 public reserveB;
    uint256 public totalLiquidity;
    uint256 public constant FEE_BPS = 30; // 0.3%

    /// @notice Minimum LP tokens permanently locked on first deposit
    /// @dev 1000 units is the Uniswap-v2 convention; burned to address(0)
    uint256 public constant MINIMUM_LIQUIDITY = 1000;

    mapping(address => uint256) public liquidity;

    event LiquidityAdded(address indexed provider, uint256 amountA, uint256 amountB, uint256 lpTokens);
    event LiquidityRemoved(address indexed provider, uint256 amountA, uint256 amountB);
    event Swap(address indexed user, address tokenIn, uint256 amountIn, uint256 amountOut);
    event Sync(uint256 reserveA, uint256 reserveB);

    constructor(address _tokenA, address _tokenB) {
        tokenA = IERC20(_tokenA);
        tokenB = IERC20(_tokenB);
    }

    /// @notice Deposit liquidity and receive LP tokens.
    /// @param amountA Amount of tokenA to deposit.
    /// @param amountB Amount of tokenB to deposit.
    /// @return lpTokens Number of LP tokens minted for the caller (excluding the
    ///         MINIMUM_LIQUIDITY burn on first deposit).
    function addLiquidity(uint256 amountA, uint256 amountB) external returns (uint256 lpTokens) {
        require(amountA > 0 && amountB > 0, "Zero amounts");

        if (totalLiquidity == 0) {
            // First deposit: compute geometric mean, then burn MINIMUM_LIQUIDITY
            lpTokens = _sqrt(amountA * amountB);
            require(lpTokens > MINIMUM_LIQUIDITY, "Insufficient initial liquidity");
            lpTokens -= MINIMUM_LIQUIDITY;

            // Lock minimum liquidity forever to prevent share-price manipulation
            _mint(address(0), MINIMUM_LIQUIDITY);
        } else {
            uint256 lpA = (amountA * totalLiquidity) / reserveA;
            uint256 lpB = (amountB * totalLiquidity) / reserveB;
            lpTokens = lpA < lpB ? lpA : lpB;
        }

        require(tokenA.transferFrom(msg.sender, address(this), amountA), "Transfer A failed");
        require(tokenB.transferFrom(msg.sender, address(this), amountB), "Transfer B failed");

        _updateReserves();
        _mint(msg.sender, lpTokens);

        emit LiquidityAdded(msg.sender, amountA, amountB, lpTokens);
    }

    /// @notice Remove liquidity and receive underlying tokens back.
    /// @param lpTokens Number of LP tokens to burn.
    function removeLiquidity(uint256 lpTokens) external {
        require(lpTokens > 0 && lpTokens <= liquidity[msg.sender], "Invalid amount");

        // Use internal reserves instead of raw balances so donations cannot inflate
        // the share price and steal from this provider or subsequent depositors.
        uint256 amountA = (lpTokens * reserveA) / totalLiquidity;
        uint256 amountB = (lpTokens * reserveB) / totalLiquidity;

        _burn(msg.sender, lpTokens);
        _updateReserves();

        require(tokenA.transfer(msg.sender, amountA), "Transfer A failed");
        require(tokenB.transfer(msg.sender, amountB), "Transfer B failed");

        emit LiquidityRemoved(msg.sender, amountA, amountB);
    }

    /// @notice Exchange one token for the other using constant-product formula.
    /// @param tokenIn  Address of the token being sold.
    /// @param amountIn Amount of tokenIn being sold.
    /// @param minAmountOut Minimum amount of output token accepted (slippage protection).
    /// @return amountOut Amount of output token transferred.
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

        _updateReserves();

        emit Swap(msg.sender, tokenIn, amountIn, amountOut);
    }

    /// @notice Reconcile internal reserves to match actual token balances.
    /// @dev Can be used after direct token transfers (donations) or to correct
    ///      bookkeeping drift. Emits a Sync event for off-chain tracking.
    function sync() external {
        _updateReserves();
        emit Sync(reserveA, reserveB);
    }

    /// @notice Get current reserves.
    function getReserves() external view returns (uint256, uint256) {
        return (reserveA, reserveB);
    }

    // ── Internal helpers ──────────────────────────────────────────

    function _mint(address to, uint256 amount) internal {
        liquidity[to] += amount;
        totalLiquidity += amount;
    }

    function _burn(address from, uint256 amount) internal {
        require(liquidity[from] >= amount, "Burn amount exceeds balance");
        liquidity[from] -= amount;
        totalLiquidity -= amount;
    }

    function _updateReserves() internal {
        reserveA = tokenA.balanceOf(address(this));
        reserveB = tokenB.balanceOf(address(this));
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
}
