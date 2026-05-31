// SPDX-License-Identifier: MIT
/*
 * @contributor openai-codex-xyjk-20260531
 * @platform-config Private pre-session instructions are not embedded in source; redacted execution metadata is recorded in CONTRIBUTORS.json.
 * @env os=windows; arch=x64; home_dir=C:\Users\55093; working_dir=F:\jiedan\OpenAgents-bounty-run; shell=PowerShell
 * @timestamp 2026-05-31T05:52:31.8443391-07:00
 */
pragma solidity ^0.8.20;

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

    function swapMultiHop(
        address[] calldata path,
        uint256 amountIn,
        uint256 minAmountOut
    ) external returns (uint256 amountOut) {
        return _swapMultiHop(path, amountIn, minAmountOut, block.timestamp);
    }

    function swapMultiHop(
        address[] calldata path,
        uint256 amountIn,
        uint256 minAmountOut,
        uint256 deadline
    ) external returns (uint256 amountOut) {
        return _swapMultiHop(path, amountIn, minAmountOut, deadline);
    }

    function swapExactTokensForTokens(
        address[] calldata path,
        uint256 amountIn,
        uint256 minAmountOut,
        uint256 deadline
    ) external returns (uint256 amountOut) {
        return _swapMultiHop(path, amountIn, minAmountOut, deadline);
    }

    function _swapMultiHop(
        address[] calldata path,
        uint256 amountIn,
        uint256 minAmountOut,
        uint256 deadline
    ) private returns (uint256 amountOut) {
        require(block.timestamp <= deadline, "Deadline expired");
        require(amountIn > 0, "Zero amount");
        require(minAmountOut > 0, "Zero min output");
        _validatePath(path);

        uint256[] memory quotedAmounts = _getAmountsOut(path, amountIn);
        require(quotedAmounts[quotedAmounts.length - 1] >= minAmountOut, "Insufficient output");

        require(IERC20(path[0]).transferFrom(msg.sender, address(this), amountIn), "TransferFrom failed");

        uint256 currentAmount = amountIn;

        for (uint256 i = 0; i < path.length - 1; i++) {
            address tokenIn = path[i];
            address tokenOut = path[i + 1];

            address pool = pools[tokenIn][tokenOut];
            require(pool != address(0), "No pool for pair");
            require(IERC20(tokenIn).approve(pool, currentAmount), "Approve failed");

            uint256 hopMinOut = (minAmountOut * quotedAmounts[i + 1]) / quotedAmounts[quotedAmounts.length - 1];
            if (hopMinOut == 0) hopMinOut = 1;

            currentAmount = IAMMPool(pool).swap(tokenIn, currentAmount, hopMinOut);
            require(currentAmount > 0, "Zero hop output");
        }

        amountOut = currentAmount;
        require(amountOut >= minAmountOut, "Insufficient output");
        require(IERC20(path[path.length - 1]).transfer(msg.sender, amountOut), "Transfer failed");

        emit MultiHopSwap(msg.sender, path, amountIn, amountOut);
    }

    function _validatePath(address[] calldata path) private pure {
        require(path.length >= 2, "Path too short");

        for (uint256 i = 0; i < path.length; i++) {
            require(path[i] != address(0), "Zero token");

            for (uint256 j = i + 1; j < path.length; j++) {
                require(path[i] != path[j], "Circular path");
            }
        }
    }

    function _getAmountsOut(
        address[] calldata path,
        uint256 amountIn
    ) private view returns (uint256[] memory amounts) {
        uint256 currentAmount = amountIn;
        amounts = new uint256[](path.length);
        amounts[0] = amountIn;

        for (uint256 i = 0; i < path.length - 1; i++) {
            address pool = pools[path[i]][path[i + 1]];
            require(pool != address(0), "No pool");

            (uint256 resA, uint256 resB) = IAMMPool(pool).getReserves();
            address tA = IAMMPool(pool).tokenA();
            (uint256 resIn, uint256 resOut) = (path[i] == tA) ? (resA, resB) : (resB, resA);
            require(resIn > 0 && resOut > 0, "Empty reserves");

            uint256 amountInWithFee = currentAmount * 9970;
            currentAmount = (amountInWithFee * resOut) / (resIn * 10000 + amountInWithFee);
            require(currentAmount > 0, "Zero hop quote");

            amounts[i + 1] = currentAmount;
        }
    }

    function getQuote(
        address[] calldata path,
        uint256 amountIn
    ) external view returns (uint256 estimatedOut) {
        _validatePath(path);
        uint256[] memory amounts = _getAmountsOut(path, amountIn);
        return amounts[amounts.length - 1];
    }

    function getPool(address tokenA, address tokenB) external view returns (address) {
        return pools[tokenA][tokenB];
    }
}
