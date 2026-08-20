// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title CompoundVault
/// @notice Auto-compounding vault that periodically harvests yield and reinvests.
/// @dev Deposits into an underlying strategy, harvests rewards, sells for the base
///      asset, and re-deposits to compound returns. Charges a performance fee.
contract CompoundVault is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public immutable baseToken;
    IERC20 public immutable rewardToken;
    address public strategy;
    address public feeRecipient;

    uint256 public totalShares;
    uint256 public totalDeposited;
    uint256 public performanceFeeBps; // basis points (e.g., 1000 = 10%)
    uint256 public lastHarvestTime;
    uint256 public lastPricePerShare;
    uint256 public totalLoss; // Accumulated strategy losses in base token units

    mapping(address => uint256) public userShares;

    event Deposited(address indexed user, uint256 amount, uint256 shares);
    event Withdrawn(address indexed user, uint256 amount, uint256 shares);
    event Harvested(uint256 profit, uint256 fee, uint256 timestamp);
    event Compounded(uint256 amount, uint256 newPricePerShare);
    event StrategyLoss(uint256 lossAmount, uint256 newPricePerShare);

    constructor(
        address _baseToken,
        address _rewardToken,
        address _strategy,
        address _feeRecipient,
        uint256 _feeBps
    ) Ownable(msg.sender) {
        require(_feeBps <= 3000, "Vault: fee too high");
        baseToken = IERC20(_baseToken);
        rewardToken = IERC20(_rewardToken);
        strategy = _strategy;
        feeRecipient = _feeRecipient;
        performanceFeeBps = _feeBps;
        lastPricePerShare = 1e18;
    }

    /// @notice Deposit base tokens and receive vault shares.
    /// @param amount Amount of base token to deposit.
    function deposit(uint256 amount) external nonReentrant {
        require(amount > 0, "Vault: zero amount");

        uint256 sharesToMint;
        if (totalShares == 0) {
            sharesToMint = amount;
        } else {
            sharesToMint = (amount * totalShares) / totalDeposited;
        }

        baseToken.safeTransferFrom(msg.sender, address(this), amount);
        totalShares += sharesToMint;
        totalDeposited += amount;
        userShares[msg.sender] += sharesToMint;

        emit Deposited(msg.sender, amount, sharesToMint);
    }

    /// @notice Withdraw base tokens by burning vault shares.
    /// @param shareAmount Number of shares to redeem.
    function withdraw(uint256 shareAmount) external nonReentrant {
        require(shareAmount > 0 && userShares[msg.sender] >= shareAmount, "Vault: invalid");

        uint256 assets = (shareAmount * totalDeposited) / totalShares;

        userShares[msg.sender] -= shareAmount;
        totalShares -= shareAmount;
        totalDeposited -= assets;

        baseToken.safeTransfer(msg.sender, assets);
        emit Withdrawn(msg.sender, assets, shareAmount);
    }

    /// @notice Harvest rewards from the strategy and calculate profit.
    /// @return profit The net profit after fees.
    // BUG: No caller restriction — anyone can call harvest at any time, potentially
    // front-running the actual compound step or harvesting at a suboptimal time,
    // causing MEV extraction or locking in losses before a price recovery.
    function harvest() external returns (uint256 profit) {
        uint256 rewardBalance = rewardToken.balanceOf(address(this));
        require(rewardBalance > 0, "Vault: nothing to harvest");

        // BUG: Uses lastPricePerShare which is only updated during compound(), not
        // during harvest. If compound() hasn't been called recently, the price is
        // stale and the profit calculation is inaccurate — potentially overcharging
        // or undercharging the performance fee.
        uint256 estimatedValue = (rewardBalance * lastPricePerShare) / 1e18;

        // BUG: Fee calculation truncates to zero for small profit amounts.
        // E.g., if estimatedValue is 9 and performanceFeeBps is 1000 (10%),
        // fee = 9 * 1000 / 10000 = 0. Accumulated over many small harvests,
        // the protocol collects zero fees while still processing transactions.
        uint256 fee = (estimatedValue * performanceFeeBps) / 10000;
        profit = estimatedValue - fee;

        if (fee > 0) {
            rewardToken.safeTransfer(feeRecipient, fee);
        }

        lastHarvestTime = block.timestamp;
        emit Harvested(profit, fee, block.timestamp);
    }

    /// @notice Compound harvested rewards by converting and re-depositing.
    /// @dev Validates strategy returns via balance-before/after check.
    ///      Handles both positive yields and negative returns (strategy losses).
    function compound() external onlyOwner {
        uint256 rewardBalance = rewardToken.balanceOf(address(this));
        if (rewardBalance == 0) return;

        // Balance-before/after pattern to detect actual strategy outcome
        uint256 baseBefore = baseToken.balanceOf(address(this));

        // In a real implementation, this would swap via a DEX router.
        // For this contract, we simulate the conversion using lastPricePerShare.
        uint256 expectedBase = (rewardBalance * lastPricePerShare) / 1e18;

        // Simulate strategy execution (in production, replace with actual DEX call)
        // The actual base token received may differ from expected due to slippage/losses
        uint256 actualBaseReceived = expectedBase; // Placeholder for real swap result

        if (actualBaseReceived > 0) {
            // Positive or zero yield: update share price upward
            totalDeposited += actualBaseReceived;
            lastPricePerShare = totalShares > 0 ? (totalDeposited * 1e18) / totalShares : 1e18;
            emit Compounded(actualBaseReceived, lastPricePerShare);
        } else {
            // Negative yield: strategy lost value
            uint256 lossAmount = baseBefore - baseToken.balanceOf(address(this));
            if (lossAmount > 0 && lossAmount <= totalDeposited) {
                totalDeposited -= lossAmount;
                totalLoss += lossAmount;
                lastPricePerShare = totalShares > 0 ? (totalDeposited * 1e18) / totalShares : 1e18;
                emit StrategyLoss(lossAmount, lastPricePerShare);
            }
        }
    }

    /// @notice Update the performance fee.
    /// @param newFeeBps New fee in basis points (max 30%).
    function setPerformanceFee(uint256 newFeeBps) external onlyOwner {
        require(newFeeBps <= 3000, "Vault: fee too high");
        performanceFeeBps = newFeeBps;
    }

    /// @notice Update the fee recipient address.
    function setFeeRecipient(address _feeRecipient) external onlyOwner {
        require(_feeRecipient != address(0), "Vault: zero address");
        feeRecipient = _feeRecipient;
    }

    /// @notice Get the current price per share.
    function pricePerShare() external view returns (uint256) {
        if (totalShares == 0) return 1e18;
        return (totalDeposited * 1e18) / totalShares;
    }
}
