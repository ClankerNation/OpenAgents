// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

interface IFlashLoanReceiver {
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 fee,
        address initiator,
        bytes calldata params
    ) external returns (bool);
}

/// @title FlashLoan
/// @notice Simple flash loan pool with minimum fee and max loan cap to prevent drainage
contract FlashLoan is ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public immutable asset;
    uint256 public totalDeposited;
    
    // Minimum fee of 1 token unit to prevent zero-fee loans on small amounts
    uint256 public constant MIN_FEE = 1;
    // Max loan is 50% of pool to prevent single-tx drainage
    uint256 public constant MAX_LOAN_BPS = 5000; // 50%
    // Fee in basis points (e.g., 9 = 0.09%)
    uint256 public feeBps;

    event FlashLoanExecuted(
        address indexed receiver,
        address indexed asset,
        uint256 amount,
        uint256 fee
    );
    event Deposited(address indexed user, uint256 amount);
    event Withdrawn(address indexed user, uint256 amount);

    constructor(address _asset, uint256 _feeBps) {
        require(_asset != address(0), "FlashLoan: zero asset");
        require(_feeBps <= 1000, "FlashLoan: fee too high"); // Max 10%
        asset = IERC20(_asset);
        feeBps = _feeBps;
    }

    /// @notice Deposit tokens into the flash loan pool
    function deposit(uint256 amount) external nonReentrant {
        require(amount > 0, "FlashLoan: zero amount");
        asset.safeTransferFrom(msg.sender, address(this), amount);
        totalDeposited += amount;
        emit Deposited(msg.sender, amount);
    }

    /// @notice Withdraw tokens from the flash loan pool
    function withdraw(uint256 amount) external nonReentrant {
        require(amount > 0 && amount <= totalDeposited, "FlashLoan: invalid amount");
        totalDeposited -= amount;
        asset.safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount);
    }

    /// @notice Execute a flash loan
    /// @param receiver Contract that will receive and return the funds
    /// @param amount Amount to borrow
    /// @param params Arbitrary data passed to the receiver
    function flashLoan(
        address receiver,
        uint256 amount,
        bytes calldata params
    ) external nonReentrant {
        require(amount > 0, "FlashLoan: zero amount");
        
        // Cap loan at 50% of pool to prevent drainage attacks
        uint256 maxLoan = (totalDeposited * MAX_LOAN_BPS) / 10000;
        require(amount <= maxLoan, "FlashLoan: exceeds max loan cap");

        // Calculate fee with minimum floor
        uint256 fee = (amount * feeBps) / 10000;
        if (fee < MIN_FEE) fee = MIN_FEE;

        uint256 balanceBefore = asset.balanceOf(address(this));
        require(balanceBefore >= amount, "FlashLoan: insufficient liquidity");

        // Transfer funds to receiver
        asset.safeTransfer(receiver, amount);

        // Execute callback
        require(
            IFlashLoanReceiver(receiver).executeOperation(
                address(asset),
                amount,
                fee,
                msg.sender,
                params
            ),
            "FlashLoan: callback failed"
        );

        // Verify repayment using internal accounting (not balanceOf)
        uint256 balanceAfter = asset.balanceOf(address(this));
        require(
            balanceAfter >= balanceBefore + fee,
            "FlashLoan: insufficient repayment"
        );

        // Update internal accounting for rebasing token safety
        totalDeposited += fee;

        emit FlashLoanExecuted(receiver, address(asset), amount, fee);
    }

    /// @notice Get available liquidity for flash loans
    function availableLiquidity() external view returns (uint256) {
        return (totalDeposited * MAX_LOAN_BPS) / 10000;
    }
}
