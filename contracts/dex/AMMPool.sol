// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor rafaio1
 * @timestamp 2026-08-20T00:00:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @title AMMPool
/// @notice Constant product (x*y=k) automated market maker pool
/// @dev Supports adding/removing liquidity and token swaps with a fee

interface IPermit2 {
    struct PermitTransferFrom {
        TokenPermissions permitted;
        uint256 nonce;
        uint256 deadline;
    }
    struct TokenPermissions {
        address token;
        uint256 amount;
    }
    function permitTransferFrom(
        PermitTransferFrom memory permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes calldata signature
    ) external;
    struct SignatureTransferDetails {
        address to;
        uint256 requestedAmount;
    }
}

contract AMMPool {
    IERC20 public tokenA;
    IERC20 public tokenB;

    uint256 public reserveA;
    uint256 public reserveB;
    uint256 public totalLiquidity;
    uint256 public constant FEE_BPS = 30; // 0.3%
    uint256 public constant MINIMUM_LIQUIDITY = 1000;

    mapping(address => uint256) public liquidity;

    event Mint(address indexed sender, uint256 amount0, uint256 amount1);
    event Burn(address indexed sender, uint256 amount0, uint256 amount1, address indexed to);
    event Swap(
        address indexed sender,
        uint256 amount0In,
        uint256 amount1In,
        uint256 amount0Out,
        uint256 amount1Out,
        address indexed to
    );
    event Sync(uint112 reserve0, uint112 reserve1);

    constructor(address _tokenA, address _tokenB) {
        tokenA = IERC20(_tokenA);
        tokenB = IERC20(_tokenB);
    }

    function addLiquidity(uint256 amountA, uint256 amountB) external returns (uint256 lpTokens) {
        require(amountA > 0 && amountB > 0, "Zero amounts");

        if (totalLiquidity == 0) {
            lpTokens = _sqrt(amountA * amountB);
            require(lpTokens > MINIMUM_LIQUIDITY, "Insufficient initial liquidity");
            
            // Lock minimum liquidity to address(0) permanently
            liquidity[address(0)] = MINIMUM_LIQUIDITY;
            totalLiquidity = MINIMUM_LIQUIDITY;
            
            lpTokens -= MINIMUM_LIQUIDITY;
        } else {
            uint256 lpA = (amountA * totalLiquidity) / reserveA;
            uint256 lpB = (amountB * totalLiquidity) / reserveB;
            lpTokens = lpA < lpB ? lpA : lpB;
        }

        require(lpTokens > 0, "Zero LP tokens");

        require(tokenA.transferFrom(msg.sender, address(this), amountA), "Transfer A failed");
        require(tokenB.transferFrom(msg.sender, address(this), amountB), "Transfer B failed");

        reserveA += amountA;
        reserveB += amountB;
        liquidity[msg.sender] += lpTokens;
        totalLiquidity += lpTokens;

        emit Mint(msg.sender, amountA, amountB);
        emit Sync(uint112(reserveA), uint112(reserveB));
    }

    function removeLiquidity(uint256 lpTokens) external {
        require(lpTokens > 0 && lpTokens <= liquidity[msg.sender], "Invalid amount");

        uint256 amountA = (lpTokens * reserveA) / totalLiquidity;
        uint256 amountB = (lpTokens * reserveB) / totalLiquidity;

        require(amountA > 0 && amountB > 0, "Zero withdrawal");

        liquidity[msg.sender] -= lpTokens;
        totalLiquidity -= lpTokens;
        reserveA -= amountA;
        reserveB -= amountB;

        require(tokenA.transfer(msg.sender, amountA), "Transfer A failed");
        require(tokenB.transfer(msg.sender, amountB), "Transfer B failed");

        emit Burn(msg.sender, amountA, amountB, msg.sender);
        emit Sync(uint112(reserveA), uint112(reserveB));
    }

    function swap(address tokenIn, uint256 amountIn, uint256 minAmountOut, uint256 deadline) external returns (uint256 amountOut) {
        require(block.timestamp <= deadline, "Swap expired");
        require(tokenIn == address(tokenA) || tokenIn == address(tokenB), "Invalid token");
        require(amountIn > 0, "Zero input");

        bool isA = tokenIn == address(tokenA);
        (uint256 resIn, uint256 resOut) = isA ? (reserveA, reserveB) : (reserveB, reserveA);

        uint256 amountInWithFee = amountIn * (10000 - FEE_BPS);
        amountOut = (amountInWithFee * resOut) / (resIn * 10000 + amountInWithFee);

        require(amountOut >= minAmountOut, "Slippage exceeded");
        require(amountOut > 0, "Zero output");

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

        // Uniswap V2 compatible Swap event signature
        if (isA) {
            emit Swap(msg.sender, amountIn, 0, 0, amountOut, msg.sender);
        } else {
            emit Swap(msg.sender, 0, amountIn, amountOut, 0, msg.sender);
        }
        emit Sync(uint112(reserveA), uint112(reserveB));
    }

    /// @notice Sync internal reserves with actual token balances
    function sync() external {
        reserveA = tokenA.balanceOf(address(this));
        reserveB = tokenB.balanceOf(address(this));
        emit Sync(uint112(reserveA), uint112(reserveB));
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
