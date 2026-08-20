// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC4626.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title YieldAggregator
/// @notice Vault that accepts deposits and allocates capital across yield strategies.
/// @dev Implements a simplified vault pattern. Users deposit a base token and receive
///      shares proportional to their ownership of the vault's total assets.
contract YieldAggregator is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    struct Strategy {
        address target;
        uint256 allocated;
        uint256 maxAllocationBps; // Max allocation in basis points (10000 = 100%)
        bool active;
    }

    IERC20 public immutable asset;
    uint256 public totalShares;
    uint256 public totalDeposited;
    mapping(address => uint256) public shares;

    Strategy[] public strategies;

    event Deposit(address indexed user, uint256 assets, uint256 sharesMinted);
    event Withdraw(address indexed user, uint256 assets, uint256 sharesBurned);
    event StrategyAdded(uint256 indexed strategyId, address target);
    event StrategyAllocated(uint256 indexed strategyId, uint256 amount);

    constructor(address _asset) Ownable(msg.sender) {
        asset = IERC20(_asset);
    }

    /// @notice Deposit tokens into the vault and receive shares.
    /// @param amount Amount of base token to deposit.
    /// @return sharesMinted Number of shares issued to the depositor.
    // BUG: No slippage check on deposit — the share price can be manipulated via
    // donation attacks (sending tokens directly to the vault) between the user's
    // approval and deposit, causing them to receive far fewer shares than expected.
    function deposit(uint256 amount) external nonReentrant returns (uint256 sharesMinted) {
        require(amount > 0, "Vault: zero deposit");

        if (totalShares == 0) {
            sharesMinted = amount;
        } else {
            sharesMinted = (amount * totalShares) / totalAssets();
        }

        asset.safeTransferFrom(msg.sender, address(this), amount);
        totalShares += sharesMinted;
        totalDeposited += amount;
        shares[msg.sender] += sharesMinted;

        emit Deposit(msg.sender, amount, sharesMinted);
    }

    /// @notice Withdraw tokens by burning vault shares.
    /// @param shareAmount Number of shares to redeem.
    /// @return assetsReturned Amount of base token returned.
    function withdraw(uint256 shareAmount) external nonReentrant returns (uint256 assetsReturned) {
        require(shareAmount > 0, "Vault: zero shares");
        require(shares[msg.sender] >= shareAmount, "Vault: insufficient shares");

        // BUG: Uses balanceOf instead of internal accounting (totalDeposited + strategy gains).
        // If tokens are donated directly to the vault or a strategy returns funds outside
        // the normal flow, this inflates the withdrawal amount, allowing early withdrawers
        // to drain more than their share at the expense of later users.
        assetsReturned = (shareAmount * asset.balanceOf(address(this))) / totalShares;

        shares[msg.sender] -= shareAmount;
        totalShares -= shareAmount;

        asset.safeTransfer(msg.sender, assetsReturned);
        emit Withdraw(msg.sender, assetsReturned, shareAmount);
    }

    /// @notice Add a new yield strategy with allocation cap.
    /// @param target Address of the strategy contract.
    /// @param maxAllocationBps Maximum allocation percentage in basis points (e.g., 3000 = 30%).
    function addStrategy(address target, uint256 maxAllocationBps) external onlyOwner {
        require(target != address(0), "Vault: zero address strategy");
        require(maxAllocationBps > 0 && maxAllocationBps <= 10000, "Vault: invalid allocation bps");
        
        strategies.push(Strategy({
            target: target,
            allocated: 0,
            maxAllocationBps: maxAllocationBps,
            active: true
        }));
        emit StrategyAdded(strategies.length - 1, target);
    }

    /// @notice Allocate vault funds to a strategy respecting allocation caps.
    /// @param strategyId Index of the strategy.
    /// @param amount Amount to allocate.
    function allocate(uint256 strategyId, uint256 amount) external onlyOwner {
        Strategy storage s = strategies[strategyId];
        require(s.active, "Vault: strategy inactive");
        require(asset.balanceOf(address(this)) >= amount, "Vault: insufficient balance");

        // Enforce per-strategy allocation limit based on current total assets
        uint256 currentTotal = totalAssets();
        uint256 maxAllowed = (currentTotal * s.maxAllocationBps) / 10000;
        require(s.allocated + amount <= maxAllowed, "Vault: exceeds max allocation");

        s.allocated += amount;
        asset.safeTransfer(s.target, amount);
        emit StrategyAllocated(strategyId, amount);
    }

    /// @notice Deactivate a strategy.
    /// @param strategyId Index of the strategy.
    function deactivateStrategy(uint256 strategyId) external onlyOwner {
        strategies[strategyId].active = false;
    }

    /// @notice Total assets under management (vault balance + allocated to strategies).
    function totalAssets() public view returns (uint256) {
        uint256 total = asset.balanceOf(address(this));
        for (uint256 i = 0; i < strategies.length; i++) {
            if (strategies[i].active) {
                total += strategies[i].allocated;
            }
        }
        return total;
    }

    /// @notice Rebalance allocations across active strategies to respect updated caps or redistribute capital.
    /// @dev Owner must manually specify new target amounts summing to <= totalAssets().
    /// @param strategyIds Array of strategy indices to rebalance.
    /// @param targetAmounts Corresponding target allocation amounts.
    function rebalance(uint256[] calldata strategyIds, uint256[] calldata targetAmounts) external onlyOwner {
        require(strategyIds.length == targetAmounts.length, "Vault: length mismatch");
        
        uint256 currentTotal = totalAssets();
        uint256 totalTarget = 0;
        
        // First pass: validate all targets and sum
        for (uint256 i = 0; i < strategyIds.length; i++) {
            Strategy storage s = strategies[strategyIds[i]];
            require(s.active, "Vault: strategy inactive");
            
            uint256 maxAllowed = (currentTotal * s.maxAllocationBps) / 10000;
            require(targetAmounts[i] <= maxAllowed, "Vault: exceeds max allocation");
            
            totalTarget += targetAmounts[i];
        }
        
        require(totalTarget <= currentTotal, "Vault: insufficient assets");
        
        // Second pass: execute transfers (simplified - assumes owner manages liquidity)
        // In production, this would pull from over-allocated strategies first
        for (uint256 i = 0; i < strategyIds.length; i++) {
            Strategy storage s = strategies[strategyIds[i]];
            if (targetAmounts[i] > s.allocated) {
                uint256 diff = targetAmounts[i] - s.allocated;
                require(asset.balanceOf(address(this)) >= diff, "Vault: insufficient liquid balance");
                s.allocated += diff;
                asset.safeTransfer(s.target, diff);
            } else if (targetAmounts[i] < s.allocated) {
                // Note: Pulling funds back requires strategy-specific withdrawal logic
                // This simplified version only tracks accounting; real impl needs IStrategy interface
                s.allocated = targetAmounts[i];
            }
            emit StrategyAllocated(strategyIds[i], s.allocated);
        }
    }

    /// @notice Preview shares for a given deposit amount.
    function previewDeposit(uint256 amount) external view returns (uint256) {
        if (totalShares == 0) return amount;
        return (amount * totalShares) / totalAssets();
    }
}
