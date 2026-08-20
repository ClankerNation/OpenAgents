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
/// @notice Flash loan provider with minimum fee enforcement, pool drainage protection,
///         internal accounting for rebasing safety, and emergency pause mechanism.
contract FlashLoan is ReentrancyGuard {
    using SafeERC20 for IERC20;

    address public owner;
    bool public paused;

    /// @notice Minimum fee in token units — ensures fee >= 1 even for tiny loans
    uint256 public constant MIN_FEE = 1;
    /// @notice Maximum loan as fraction of pool balance (50% = 5000 bps)
    uint256 public constant MAX_LOAN_BPS = 5000;
    /// @notice Fee in basis points (e.g., 9 = 0.09%)
    uint256 public feeBps;

    /// @notice Internal accounting of deposited assets per token
    mapping(address => uint256) public internalBalance;

    event FlashLoanExecuted(
        address indexed asset,
        address indexed initiator,
        uint256 amount,
        uint256 fee
    );
    event Deposited(address indexed token, address indexed depositor, uint256 amount);
    event Withdrawn(address indexed token, address indexed withdrawer, uint256 amount);
    event Paused();
    event Unpaused();

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "Contract paused");
        _;
    }

    constructor(uint256 _feeBps) {
        owner = msg.sender;
        feeBps = _feeBps;
    }

    /// @notice Deposit tokens into the flash loan pool.
    /// @param token The ERC20 token to deposit.
    /// @param amount Amount to deposit.
    function deposit(address token, uint256 amount) external whenNotPaused {
        require(amount > 0, "Zero amount");
        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);
        internalBalance[token] += amount;
        emit Deposited(token, msg.sender, amount);
    }

    /// @notice Withdraw tokens from the flash loan pool.
    /// @param token The ERC20 token to withdraw.
    /// @param amount Amount to withdraw.
    function withdraw(address token, uint256 amount) external onlyOwner {
        require(amount > 0, "Zero amount");
        require(internalBalance[token] >= amount, "Insufficient internal balance");
        internalBalance[token] -= amount;
        IERC20(token).safeTransfer(msg.sender, amount);
        emit Withdrawn(token, msg.sender, amount);
    }

    /// @notice Execute a flash loan. Borrower must return amount + fee within same tx.
    /// @param asset Token to borrow.
    /// @param amount Amount to borrow.
    /// @param receiver Contract implementing IFlashLoanReceiver.
    /// @param params Arbitrary data passed to receiver.
    function flashLoan(
        address asset,
        uint256 amount,
        address receiver,
        bytes calldata params
    ) external nonReentrant whenNotPaused {
        require(amount > 0, "Zero loan amount");

        // FIX: Max loan cap — cannot borrow more than 50% of pool
        uint256 poolBalance = internalBalance[asset];
        require(poolBalance > 0, "No liquidity");
        uint256 maxLoan = (poolBalance * MAX_LOAN_BPS) / 10000;
        require(amount <= maxLoan, "Exceeds max loan (50% of pool)");

        // Calculate fee with minimum enforcement
        uint256 fee = (amount * feeBps) / 10000;
        if (fee < MIN_FEE) {
            fee = MIN_FEE;
        }

        uint256 balanceBefore = IERC20(asset).balanceOf(address(this));

        // Transfer loan to receiver
        IERC20(asset).safeTransfer(receiver, amount);

        // Execute borrower callback
        require(
            IFlashLoanReceiver(receiver).executeOperation(asset, amount, fee, msg.sender, params),
            "Flash loan callback failed"
        );

        // Verify repayment: balance must be >= balanceBefore + fee
        uint256 balanceAfter = IERC20(asset).balanceOf(address(this));
        require(balanceAfter >= balanceBefore + fee, "Insufficient repayment");

        // Update internal accounting with profit (fee)
        uint256 profit = balanceAfter - balanceBefore;
        internalBalance[asset] += profit;

        emit FlashLoanExecuted(asset, msg.sender, amount, fee);
    }

    /// @notice Emergency pause — blocks all flash loans and deposits.
    function pause() external onlyOwner {
        paused = true;
        emit Paused();
    }

    /// @notice Unpause the contract.
    function unpause() external onlyOwner {
        paused = false;
        emit Unpaused();
    }

    /// @notice Update fee basis points.
    /// @param _feeBps New fee in basis points.
    function setFee(uint256 _feeBps) external onlyOwner {
        feeBps = _feeBps;
    }

    /// @notice Get available liquidity for a token using internal accounting.
    /// @param token The token address.
    /// @return Available balance from internal tracking (rebasing-safe).
    function getAvailableLiquidity(address token) external view returns (uint256) {
        return internalBalance[token];
    }
}
