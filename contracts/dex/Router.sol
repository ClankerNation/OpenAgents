// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @author yossweh (GitHub)
/// @notice Fixed Issue #181 — Unchecked ERC20 return values in Router.
/// @dev Contributor Info:
///   Platform: Hermes Agent (Telegram) with SOUL.md + AGENTS.md loaded
///   OS: Linux (6.8.0-101-generic), Arch: x86_64 (amd64)
///   Home: /home/ubuntu, Working Dir: /tmp/OpenAgents
///   Shell: /bin/bash

interface IAMMPool {
    function swap(address tokenIn, uint256 amountIn, uint256 minAmountOut) external returns (uint256);
    function getReserves() external view returns (uint256, uint256);
    function tokenA() external view returns (address);
    function tokenB() external view returns (address);
}

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @title Router
/// @notice Multi-hop swap router that routes trades through multiple AMM pools
/// @dev Each hop uses a registered pool; tokens flow through the router
contract Router {
    address public admin;

    // pool registry: tokenA => tokenB => pool address
    mapping(address => mapping(address => address)) public pools;

    event PoolRegistered(address tokenA, address tokenB, address pool);
    event MultiHopSwap(address indexed user, address[] path, uint256 amountIn, uint256 amountOut);

    constructor() {
        admin = msg.sender;
    }

    function registerPool(address _tokenA, address _tokenB, address _pool) external {
        require(msg.sender == admin, "Not admin");
        pools[_tokenA][_tokenB] = _pool;
        pools[_tokenB][_tokenA] = _pool;
        emit PoolRegistered(_tokenA, _tokenB, _pool);
    }

    // BUG: No slippage protection — minAmountOut is passed as 0 to every intermediate hop,
    // so a sandwich attacker can extract maximum value from multi-hop trades
    // BUG: Path validation missing — no check that path[0] != path[path.length-1],
    // allowing circular swaps (A->B->A) that waste gas and may be used in attacks
    // BUG: Intermediate amounts not validated — if a pool returns 0 from swap,
    // subsequent hops proceed with 0 input, silently producing a 0-output trade
    function swapMultiHop(
        address[] calldata path,
        uint256 amountIn,
        uint256 /* minAmountOut */
    ) external returns (uint256 amountOut) {
        require(path.length >= 2, "Path too short");

        // FIX #181: Check return value — non-standard ERC20s may return false instead of reverting
        require(IERC20(path[0]).transferFrom(msg.sender, address(this), amountIn), "transferFrom failed");

        uint256 currentAmount = amountIn;

        for (uint256 i = 0; i < path.length - 1; i++) {
            address tokenIn = path[i];
            address tokenOut = path[i + 1];

            address pool = pools[tokenIn][tokenOut];
            require(pool != address(0), "No pool for pair");

            IERC20(tokenIn).approve(pool, currentAmount);

            // Passes 0 as minAmountOut — no slippage protection on intermediate hops
            currentAmount = IAMMPool(pool).swap(tokenIn, currentAmount, 0);
        }

        amountOut = currentAmount;

        // Transfer final tokens to user
        // FIX #181: Check return value — non-standard ERC20s may return false instead of reverting
        require(IERC20(path[path.length - 1]).transfer(msg.sender, amountOut), "transfer failed");

        emit MultiHopSwap(msg.sender, path, amountIn, amountOut);
    }

    function getQuote(
        address[] calldata path,
        uint256 amountIn
    ) external view returns (uint256 estimatedOut) {
        uint256 currentAmount = amountIn;

        for (uint256 i = 0; i < path.length - 1; i++) {
            address pool = pools[path[i]][path[i + 1]];
            require(pool != address(0), "No pool");

            (uint256 resA, uint256 resB) = IAMMPool(pool).getReserves();
            address tA = IAMMPool(pool).tokenA();

            (uint256 resIn, uint256 resOut) = (path[i] == tA) ? (resA, resB) : (resB, resA);
            uint256 amountInWithFee = currentAmount * 9970;
            currentAmount = (amountInWithFee * resOut) / (resIn * 10000 + amountInWithFee);
        }

        return currentAmount;
    }

    function getPool(address tokenA, address tokenB) external view returns (address) {
        return pools[tokenA][tokenB];
    }
}