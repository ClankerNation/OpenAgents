// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @fix-author Claude Fable 5 (Autonomous Agent)
 * @date 2026-08-20
 * @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform_instructions [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */

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

    /// @notice Execute a multi-hop swap with slippage protection and deadline.
    /// @param path Array of token addresses to route through.
    /// @param amountIn Amount of the first token to swap.
    /// @param minAmountsOut Array of minimum amounts out for each hop (length must be path.length - 1).
    /// @param deadline Unix timestamp after which the transaction reverts.
    function swapMultiHop(
        address[] calldata path,
        uint256 amountIn,
        uint256[] calldata minAmountsOut,
        uint256 deadline
    ) external returns (uint256 amountOut) {
        require(block.timestamp <= deadline, "Router: transaction expired");
        require(path.length >= 2, "Router: path too short");
        require(minAmountsOut.length == path.length - 1, "Router: invalid minAmountsOut length");
        require(amountIn > 0, "Router: zero amount in");
        
        // Reject circular paths and duplicate tokens
        for (uint256 i = 0; i < path.length; i++) {
            require(path[i] != address(0), "Router: zero address in path");
            for (uint256 j = i + 1; j < path.length; j++) {
                require(path[i] != path[j], "Router: circular or duplicate path");
            }
        }

        IERC20(path[0]).transferFrom(msg.sender, address(this), amountIn);

        uint256 currentAmount = amountIn;

        for (uint256 i = 0; i < path.length - 1; i++) {
            address tokenIn = path[i];
            address tokenOut = path[i + 1];

            address pool = pools[tokenIn][tokenOut];
            require(pool != address(0), "Router: no pool for pair");

            IERC20(tokenIn).approve(pool, currentAmount);

            uint256 minOut = minAmountsOut[i];
            currentAmount = IAMMPool(pool).swap(tokenIn, currentAmount, minOut);
            
            // Ensure non-zero intermediate and final amounts
            require(currentAmount > 0, "Router: zero output amount");
        }

        amountOut = currentAmount;

        // Transfer final tokens to user
        IERC20(path[path.length - 1]).transfer(msg.sender, amountOut);

        emit MultiHopSwap(msg.sender, path, amountIn, amountOut);
    }

    function getQuote(
        address[] calldata path,
        uint256 amountIn
    ) external view returns (uint256 estimatedOut) {
        require(path.length >= 2, "Router: path too short");
        uint256 currentAmount = amountIn;

        for (uint256 i = 0; i < path.length - 1; i++) {
            address pool = pools[path[i]][path[i + 1]];
            require(pool != address(0), "Router: no pool");

            (uint256 resA, uint256 resB) = IAMMPool(pool).getReserves();
            address tA = IAMMPool(pool).tokenA();

            (uint256 resIn, uint256 resOut) = (path[i] == tA) ? (resA, resB) : (resB, resA);
            require(resIn > 0 && resOut > 0, "Router: pool empty");
            
            uint256 amountInWithFee = currentAmount * 9970;
            currentAmount = (amountInWithFee * resOut) / (resIn * 10000 + amountInWithFee);
        }

        return currentAmount;
    }

    function getPool(address tokenA, address tokenB) external view returns (address) {
        return pools[tokenA][tokenB];
    }
}
