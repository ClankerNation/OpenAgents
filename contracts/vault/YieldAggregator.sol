// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title YieldAggregator
/// @notice Vault that accepts deposits and allocates capital across yield strategies.
/// @dev Implements a simplified vault pattern. Users deposit a base token and receive
///      shares proportional to their ownership of the vault's internally accounted assets.
/// @custom:contributor Bounty #95 - donation-attack hardening with minShares and accounting guards.
contract YieldAggregator is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    struct Strategy {
        address target;
        uint256 allocated;
        bool active;
    }

    uint256 public constant MAX_PRICE_DEVIATION_BPS = 500;
    uint256 private constant BPS_DENOMINATOR = 10000;

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
        require(_asset != address(0), "Vault: zero asset");
        asset = IERC20(_asset);
    }

    /// @notice Deposit tokens into the vault and receive shares.
    /// @param amount Amount of base token to deposit.
    /// @param minShares Minimum acceptable shares to mint.
    /// @return sharesMinted Number of shares issued to the depositor.
    function deposit(uint256 amount, uint256 minShares) external nonReentrant returns (uint256 sharesMinted) {
        require(amount > 0, "Vault: zero deposit");
        _assertPriceDeviationWithinLimit();

        uint256 accountedAssets = totalDeposited;
        if (totalShares == 0) {
            sharesMinted = amount;
        } else {
            require(accountedAssets > 0, "Vault: no accounted assets");
            sharesMinted = (amount * totalShares) / accountedAssets;
        }
        require(sharesMinted > 0, "Vault: zero shares");
        require(sharesMinted >= minShares, "Vault: slippage");

        asset.safeTransferFrom(msg.sender, address(this), amount);
        totalShares += sharesMinted;
        totalDeposited = accountedAssets + amount;
        shares[msg.sender] += sharesMinted;

        emit Deposit(msg.sender, amount, sharesMinted);
    }

    /// @notice Withdraw tokens by burning vault shares.
    /// @param shareAmount Number of shares to redeem.
    /// @return assetsReturned Amount of base token returned.
    function withdraw(uint256 shareAmount) external nonReentrant returns (uint256 assetsReturned) {
        require(shareAmount > 0, "Vault: zero shares");
        require(shares[msg.sender] >= shareAmount, "Vault: insufficient shares");
        _assertPriceDeviationWithinLimit();

        assetsReturned = (shareAmount * totalDeposited) / totalShares;

        shares[msg.sender] -= shareAmount;
        totalShares -= shareAmount;
        totalDeposited -= assetsReturned;

        asset.safeTransfer(msg.sender, assetsReturned);
        emit Withdraw(msg.sender, assetsReturned, shareAmount);
    }

    /// @notice Add a new yield strategy.
    /// @param target Address of the strategy contract.
    function addStrategy(address target) external onlyOwner {
        require(target != address(0), "Vault: zero strategy");
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
        _assertPriceDeviationWithinLimit();

        uint256 availableAccountedAssets = totalDeposited - _allocatedAssets();
        require(availableAccountedAssets >= amount, "Vault: insufficient balance");

        s.allocated += amount;
        asset.safeTransfer(s.target, amount);
        emit StrategyAllocated(strategyId, amount);
    }

    /// @notice Deactivate a strategy.
    /// @param strategyId Index of the strategy.
    function deactivateStrategy(uint256 strategyId) external onlyOwner {
        strategies[strategyId].active = false;
    }

    /// @notice Total internally accounted assets under management.
    function totalAssets() public view returns (uint256) {
        return totalDeposited;
    }

    /// @notice Current token balance plus internally allocated strategy principal.
    function actualManagedAssets() external view returns (uint256) {
        return _actualManagedAssets();
    }

    /// @notice Preview shares for a given deposit amount.
    function previewDeposit(uint256 amount) external view returns (uint256) {
        if (totalShares == 0) return amount;
        return (amount * totalShares) / totalDeposited;
    }

    function _actualManagedAssets() internal view returns (uint256) {
        return asset.balanceOf(address(this)) + _allocatedAssets();
    }

    function _allocatedAssets() internal view returns (uint256 totalAllocated) {
        for (uint256 i = 0; i < strategies.length; i++) {
            totalAllocated += strategies[i].allocated;
        }
    }

    function _assertPriceDeviationWithinLimit() internal view {
        uint256 accountedAssets = totalDeposited;
        uint256 actualAssets = _actualManagedAssets();

        if (accountedAssets == 0) {
            require(actualAssets == 0, "Vault: price deviation");
            return;
        }

        uint256 deviation = actualAssets > accountedAssets
            ? actualAssets - accountedAssets
            : accountedAssets - actualAssets;
        require(
            deviation * BPS_DENOMINATOR <= accountedAssets * MAX_PRICE_DEVIATION_BPS,
            "Vault: price deviation"
        );
    }
}
