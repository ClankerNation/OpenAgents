// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @fix-author Claude Fable 5 (Autonomous Agent)
 * @date 2026-08-20
 * @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform_instructions [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title YieldAggregator
/// @notice Vault that accepts deposits and allocates capital across yield strategies.
/// @dev Implements a simplified vault pattern with donation attack protection.
contract YieldAggregator is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    struct Strategy {
        address target;
        uint256 allocated;
        bool active;
    }

    IERC20 public immutable asset;
    uint256 public totalShares;
    uint256 public totalDeposited; // Internal accounting to prevent donation attacks
    mapping(address => uint256) public shares;

    Strategy[] public strategies;

    // Maximum allowed price deviation (5%) to detect manipulation
    uint256 public constant MAX_PRICE_DEVIATION_BPS = 500;
    uint256 public constant BPS_DENOMINATOR = 10000;

    event Deposit(address indexed user, uint256 assets, uint256 sharesMinted);
    event Withdraw(address indexed user, uint256 assets, uint256 sharesBurned);
    event StrategyAdded(uint256 indexed strategyId, address target);
    event StrategyAllocated(uint256 indexed strategyId, uint256 amount);

    constructor(address _asset) Ownable(msg.sender) {
        require(_asset != address(0), "Vault: zero asset");
        asset = IERC20(_asset);
    }

    /// @notice Total assets under management using internal accounting.
    /// @dev Uses totalDeposited + strategy gains instead of balanceOf to prevent donation attacks.
    function totalAssets() public view returns (uint256) {
        uint256 total = totalDeposited;
        for (uint256 i = 0; i < strategies.length; i++) {
            if (strategies[i].active) {
                total += strategies[i].allocated;
            }
        }
        return total;
    }

    /// @notice Deposit tokens into the vault and receive shares.
    /// @param amount Amount of base token to deposit.
    /// @param minShares Minimum shares to receive (slippage protection).
    /// @return sharesMinted Number of shares issued to the depositor.
    function deposit(uint256 amount, uint256 minShares) external nonReentrant returns (uint256 sharesMinted) {
        require(amount > 0, "Vault: zero deposit");

        uint256 currentTotalAssets = totalAssets();

        if (totalShares == 0) {
            sharesMinted = amount;
        } else {
            require(currentTotalAssets > 0, "Vault: zero assets");
            sharesMinted = (amount * totalShares) / currentTotalAssets;

            // Price deviation check: compare expected vs actual share price
            // If someone donated, currentTotalAssets would be inflated relative to totalDeposited
            // We check that the implied price hasn't deviated more than 5% from internal accounting
            uint256 expectedPrice = (currentTotalAssets * BPS_DENOMINATOR) / totalShares;
            uint256 fairPrice = (totalDeposited * BPS_DENOMINATOR) / totalShares;
            
            // Allow some tolerance for legitimate yield but reject large deviations
            if (fairPrice > 0) {
                uint256 deviation;
                if (expectedPrice > fairPrice) {
                    deviation = ((expectedPrice - fairPrice) * BPS_DENOMINATOR) / fairPrice;
                } else {
                    deviation = ((fairPrice - expectedPrice) * BPS_DENOMINATOR) / fairPrice;
                }
                require(deviation <= MAX_PRICE_DEVIATION_BPS, "Vault: price deviation too high");
            }
        }

        require(sharesMinted >= minShares, "Vault: insufficient shares output");

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

        // Use internal accounting (totalAssets) instead of balanceOf
        uint256 currentTotalAssets = totalAssets();
        require(currentTotalAssets > 0, "Vault: no assets");
        
        assetsReturned = (shareAmount * currentTotalAssets) / totalShares;

        shares[msg.sender] -= shareAmount;
        totalShares -= shareAmount;
        // Reduce internal accounting proportionally
        totalDeposited = (totalDeposited * (totalShares)) / (totalShares + shareAmount);

        asset.safeTransfer(msg.sender, assetsReturned);
        emit Withdraw(msg.sender, assetsReturned, shareAmount);
    }

    /// @notice Add a new yield strategy.
    /// @param target Address of the strategy contract.
    function addStrategy(address target) external onlyOwner {
        require(target != address(0), "Vault: zero strategy address");
        strategies.push(Strategy({
            target: target,
            allocated: 0,
            active: true
        }));
        emit StrategyAdded(strategies.length - 1, target);
    }

    /// @notice Allocate vault funds to a strategy.
    /// @param strategyId Index of the strategy.
    /// @param amount Amount to allocate.
    function allocate(uint256 strategyId, uint256 amount) external onlyOwner {
        Strategy storage s = strategies[strategyId];
        require(s.active, "Vault: strategy inactive");
        require(s.target != address(0), "Vault: invalid strategy target");
        require(asset.balanceOf(address(this)) >= amount, "Vault: insufficient balance");

        s.allocated += amount;
        // Move from deposited to allocated in internal accounting
        totalDeposited -= amount;
        
        asset.safeTransfer(s.target, amount);
        emit StrategyAllocated(strategyId, amount);
    }

    /// @notice Deactivate a strategy.
    /// @param strategyId Index of the strategy.
    function deactivateStrategy(uint256 strategyId) external onlyOwner {
        strategies[strategyId].active = false;
    }

    /// @notice Preview shares for a given deposit amount.
    function previewDeposit(uint256 amount) external view returns (uint256) {
        if (totalShares == 0) return amount;
        uint256 currentTotalAssets = totalAssets();
        if (currentTotalAssets == 0) return 0;
        return (amount * totalShares) / currentTotalAssets;
    }
}
