// SPDX-License-Identifier: MIT
/*
 * @contributor-info openai-codex-xyjk-20260531
 * @platform-config Private pre-session instructions are not embedded in source; redacted execution metadata is recorded in CONTRIBUTORS.json.
 * @env os=windows; arch=x64; home_dir=C:\Users\55093; working_dir=F:\jiedan\OpenAgents-bounty-run; shell=PowerShell
 * @timestamp 2026-05-31T06:06:02.9251807-07:00
 */
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

    uint256 public constant MAX_BPS = 10_000;

    struct Strategy {
        address target;
        uint256 allocated;
        uint256 maxAllocationBps;
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
    event StrategyRebalanced(uint256 indexed strategyId, uint256 amount);

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

        _allocateAvailable();

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

    /// @notice Add a new yield strategy.
    /// @param target Address of the strategy contract.
    // BUG: Strategy target can be zero address — allocating funds to address(0)
    // would burn them permanently via the external call.
    function addStrategy(address target) external onlyOwner {
        addStrategy(target, MAX_BPS);
    }

    function addStrategy(address target, uint256 maxAllocationBps) public onlyOwner {
        require(target != address(0), "Vault: zero strategy");
        require(maxAllocationBps <= MAX_BPS, "Vault: cap too high");
        strategies.push(Strategy({
            target: target,
            allocated: 0,
            maxAllocationBps: maxAllocationBps,
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
        require(asset.balanceOf(address(this)) >= amount, "Vault: insufficient balance");
        require(s.allocated + amount <= _strategyCapAmount(s), "Vault: allocation cap exceeded");

        s.allocated += amount;
        asset.safeTransfer(s.target, amount);
        emit StrategyAllocated(strategyId, amount);
    }

    function rebalance() external onlyOwner {
        _allocateAvailable();
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

    /// @notice Preview shares for a given deposit amount.
    function previewDeposit(uint256 amount) external view returns (uint256) {
        if (totalShares == 0) return amount;
        return (amount * totalShares) / totalAssets();
    }

    function strategyCount() external view returns (uint256) {
        return strategies.length;
    }

    function currentAllocation(uint256 strategyId) external view returns (uint256) {
        return strategies[strategyId].allocated;
    }

    function maxAllocation(uint256 strategyId) external view returns (uint256) {
        return _strategyCapAmount(strategies[strategyId]);
    }

    function _allocateAvailable() private {
        uint256 remaining = asset.balanceOf(address(this));
        for (uint256 i = 0; i < strategies.length && remaining > 0; i++) {
            Strategy storage s = strategies[i];
            if (!s.active) continue;

            uint256 cap = _strategyCapAmount(s);
            if (s.allocated >= cap) continue;

            uint256 amount = cap - s.allocated;
            if (amount > remaining) amount = remaining;

            s.allocated += amount;
            remaining -= amount;
            asset.safeTransfer(s.target, amount);
            emit StrategyRebalanced(i, amount);
        }
    }

    function _strategyCapAmount(Strategy memory s) private view returns (uint256) {
        return (totalDeposited * s.maxAllocationBps) / MAX_BPS;
    }
}
