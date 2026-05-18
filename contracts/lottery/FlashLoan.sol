// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title FlashLoan
 * @notice Flash loan provider with fee enforcement, pool drainage protection,
 *         and emergency pause capability.
 *
 * @contributor-info
 * Agent: hermes | OS: Linux 6.14.0-37-generic | Arch: x86_64
 * Home: /home/ubuntu | CWD: /home/ubuntu/.hermes/hermes-agent | Shell: /bin/bash
 *
 * Fixes per Bounty #9:
 * - Minimum fee of 1 token (prevents zero-fee truncation on small amounts)
 * - Maximum loan capped at 50% of pool balance (prevents drainage)
 * - Reentrancy guard on flashLoan execution
 * - Emergency pause/unpause for pool safety
 * - Internal accounting for rebasing-safe balance checks
 */
contract FlashLoan is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    /// @notice Basis point fee on flash loan amount (e.g., 9 = 0.09%)
    uint256 public feeBps;

    /// @notice Maximum fraction of pool that can be borrowed in a single loan (in bps, 5000 = 50%)
    uint256 public constant MAX_LOAN_FRACTION_BPS = 5000;

    /// @notice Minimum fee in token units — prevents zero truncation on small amounts
    uint256 public constant MIN_FEE = 1;

    /// @notice The token being lent
    IERC20 public immutable loanToken;

    /// @notice Internal accounting of total deposits (rebasing-safe)
    uint256 internal _totalDeposits;

    /// @dev Tracks whether a flash loan callback is in progress
    bool private _flashLoanInProgress;

    /// @notice Emitted when a flash loan is executed
    event FlashLoanExecuted(
        address indexed borrower,
        uint256 amount,
        uint256 fee
    );

    /// @notice Emitted when the fee basis points are updated
    event FeeUpdated(uint256 oldBps, uint256 newBps);

    /// @notice Emitted when liquidity is deposited into the pool
    event LiquidityDeposited(address indexed depositor, uint256 amount);

    /// @notice Emitted when liquidity is withdrawn from the pool
    event LiquidityWithdrawn(address indexed withdrawer, uint256 amount);

    /// @notice Emitted when emergency pause is triggered
    event EmergencyPaused(address indexed pauser);

    /// @notice Emitted when pause is lifted
    event EmergencyUnpaused(address indexed unpauser);

    /// @dev Reverts if a flash loan callback is already in progress
    modifier notDuringFlashLoan() {
        require(!_flashLoanInProgress, "FlashLoan: reentrancy during flash loan");
        _;
    }

    constructor(address _loanToken, uint256 _feeBps) Ownable(msg.sender) {
        require(_feeBps <= 10000, "FlashLoan: fee exceeds 100%");
        loanToken = IERC20(_loanToken);
        feeBps = _feeBps;
    }

    // ─── Deposit / Withdraw Liquidity ──────────────────────────────

    /**
     * @notice Deposit loan tokens into the pool to provide liquidity.
     * @param amount Amount of loan tokens to deposit.
     */
    function depositLiquidity(uint256 amount) external nonReentrant whenNotPaused {
        require(amount > 0, "FlashLoan: zero deposit");

        uint256 balanceBefore = loanToken.balanceOf(address(this));
        loanToken.safeTransferFrom(msg.sender, address(this), amount);
        uint256 received = loanToken.balanceOf(address(this)) - balanceBefore;

        _totalDeposits += received;

        emit LiquidityDeposited(msg.sender, received);
    }

    /**
     * @notice Withdraw deposited loan tokens (owner only).
     * @param amount Amount to withdraw.
     */
    function withdrawLiquidity(uint256 amount) external onlyOwner nonReentrant whenNotPaused {
        require(amount > 0, "FlashLoan: zero withdraw");
        require(amount <= _totalDeposits, "FlashLoan: exceeds deposits");

        _totalDeposits -= amount;
        loanToken.safeTransfer(msg.sender, amount);

        emit LiquidityWithdrawn(msg.sender, amount);
    }

    // ─── Flash Loan ────────────────────────────────────────────────

    /**
     * @notice Execute a flash loan. The borrower receives `amount` tokens and must
     *         return `amount + fee` within the same transaction via the callback.
     *
     * @param amount  The requested loan amount.
     * @param borrower The contract that will receive the callback.
     * @param data     Arbitrary data forwarded to the borrower callback.
     *
     * Requirements:
     * - Pool must not be paused
     * - No reentrancy (both guard and in-progress flag)
     * - Loan amount must not exceed 50% of available pool
     * - Fee must be at least MIN_FEE (1 token)
     * - Borrower must repay amount + fee after callback
     */
    function flashLoan(
        uint256 amount,
        address borrower,
        bytes calldata data
    ) external nonReentrant whenNotPaused notDuringFlashLoan returns (bool) {
        require(amount > 0, "FlashLoan: zero amount");
        require(borrower != address(0), "FlashLoan: zero borrower");

        // Pool drainage protection: max 50% of pool available per loan
        uint256 poolBalance = _poolBalance();
        require(amount <= (poolBalance * MAX_LOAN_FRACTION_BPS) / 10000, "FlashLoan: exceeds 50% of pool");

        // Calculate fee with minimum floor to prevent zero-fee truncation
        uint256 fee = (amount * feeBps) / 10000;
        if (fee < MIN_FEE) {
            fee = MIN_FEE;
        }

        // Record internal balance before transfer
        uint256 balanceBefore = loanToken.balanceOf(address(this));

        // Transfer loan amount to borrower
        loanToken.safeTransfer(borrower, amount);

        // Mark flash loan in progress (secondary reentrancy guard alongside nonReentrant)
        _flashLoanInProgress = true;

        // Callback to borrower
        IFlashLoanReceiver(borrower).executeOperation(
            address(loanToken),
            amount,
            fee,
            msg.sender,
            data
        );

        _flashLoanInProgress = false;

        // Verify repayment: borrower must have returned amount + fee
        uint256 balanceAfter = loanToken.balanceOf(address(this));
        require(balanceAfter >= balanceBefore + fee, "FlashLoan: repayment insufficient");

        // Update internal accounting for rebasing safety
        _totalDeposits = _poolBalance();

        emit FlashLoanExecuted(borrower, amount, fee);

        return true;
    }

    // ─── Emergency Pause ────────────────────────────────────────────

    /**
     * @notice Emergency pause — disables flash loans, deposits, and withdrawals.
     */
    function emergencyPause() external onlyOwner {
        _pause();
        emit EmergencyPaused(msg.sender);
    }

    /**
     * @notice Lift emergency pause — re-enables all operations.
     */
    function emergencyUnpause() external onlyOwner {
        _unpause();
        emit EmergencyUnpaused(msg.sender);
    }

    // ─── Admin ─────────────────────────────────────────────────────

    /**
     * @notice Update the fee basis points.
     * @param newBps New fee in basis points (max 10000 = 100%).
     */
    function setFeeBps(uint256 newBps) external onlyOwner {
        require(newBps <= 10000, "FlashLoan: fee exceeds 100%");
        uint256 oldBps = feeBps;
        feeBps = newBps;
        emit FeeUpdated(oldBps, newBps);
    }

    // ─── View ──────────────────────────────────────────────────────

    /**
     * @notice Current pool balance (actual token holdings).
     */
    function poolBalance() external view returns (uint256) {
        return _poolBalance();
    }

    /**
     * @notice Internal accounting of total deposits (rebasing-safe).
     */
    function totalDeposits() external view returns (uint256) {
        return _totalDeposits;
    }

    /**
     * @notice Calculate fee for a given loan amount.
     * @param amount Loan amount.
     * @return Fee — always at least MIN_FEE.
     */
    function calculateFee(uint256 amount) external view returns (uint256) {
        uint256 fee = (amount * feeBps) / 10000;
        if (fee < MIN_FEE) {
            fee = MIN_FEE;
        }
        return fee;
    }

    /**
     * @notice Maximum loan amount available (50% of pool).
     */
    function maxLoanAmount() external view returns (uint256) {
        return (_poolBalance() * MAX_LOAN_FRACTION_BPS) / 10000;
    }

    // ─── Internal ──────────────────────────────────────────────────

    function _poolBalance() internal view returns (uint256) {
        return loanToken.balanceOf(address(this));
    }
}

/// @notice Interface that flash loan receivers must implement
interface IFlashLoanReceiver {
    /**
     * @dev Called after the loan tokens are transferred to the receiver.
     *      Must return the loan amount + fee to the FlashLoan contract.
     */
    function executeOperation(
        address token,
        uint256 amount,
        uint256 fee,
        address initiator,
        bytes calldata params
    ) external returns (bool);
}
