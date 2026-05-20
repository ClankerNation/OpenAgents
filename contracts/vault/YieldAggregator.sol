// SPDX-License-Identifier: MIT
// @contributor cursor-auto-agent
// @platform-config Cursor Agent session — ION DEX / OpenAgents bounty #21. Rules: UTF-8 source, Hardhat verify before PR.
// @env os=Windows_NT, arch=x64, home=C:\Users\admin, working_dir=D:\openclaw-tools\OpenAgents, shell=powershell
// @timestamp 2026-05-20T12:00:00Z
// @bounty ClankerNation/OpenAgents#21 — donation attack on YieldAggregator deposit
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title YieldAggregator
/// @notice Vault that accepts deposits and allocates capital across yield strategies.
/// @dev Share mint/burn uses internal accounting (totalDeposited + strategyReturns) so direct
///      token donations cannot inflate share price or withdrawal payouts.
contract YieldAggregator is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    /// @notice Max vault balance excess over internal assets before withdraw reverts (5% = 500 bps).
    uint256 public constant MAX_PRICE_DEVIATION_BPS = 500;

    struct Strategy {
        address target;
        uint256 allocated;
        bool active;
    }

    IERC20 public immutable asset;
    uint256 public totalShares;
    uint256 public totalDeposited;
    uint256 public strategyReturns;
    mapping(address => uint256) public shares;

    Strategy[] public strategies;

    event Deposit(address indexed user, uint256 assets, uint256 sharesMinted);
    event Withdraw(address indexed user, uint256 assets, uint256 sharesBurned);
    event StrategyAdded(uint256 indexed strategyId, address target);
    event StrategyAllocated(uint256 indexed strategyId, uint256 amount);
    event StrategyReturnsReported(uint256 amount);

    constructor(address _asset) Ownable(msg.sender) {
        require(_asset != address(0), "Vault: zero asset");
        asset = IERC20(_asset);
    }

    /// @notice Assets tracked for share pricing (excludes unsolicited donations).
    function internalAssets() public view returns (uint256) {
        return totalDeposited + strategyReturns;
    }

    /// @notice Deposit tokens into the vault and receive shares.
    /// @param amount Amount of base token to deposit.
    /// @param minShares Minimum shares expected (slippage / donation front-run protection).
    function deposit(uint256 amount, uint256 minShares) external nonReentrant returns (uint256 sharesMinted) {
        require(amount > 0, "Vault: zero deposit");
        require(minShares > 0, "Vault: zero minShares");

        uint256 accounted = internalAssets();
        if (totalShares == 0) {
            sharesMinted = amount;
        } else {
            sharesMinted = (amount * totalShares) / accounted;
        }

        require(sharesMinted >= minShares, "Vault: insufficient shares minted");

        asset.safeTransferFrom(msg.sender, address(this), amount);
        totalShares += sharesMinted;
        totalDeposited += amount;
        shares[msg.sender] += sharesMinted;

        emit Deposit(msg.sender, amount, sharesMinted);
    }

    /// @notice Withdraw tokens by burning vault shares.
    /// @param shareAmount Number of shares to redeem.
    function withdraw(uint256 shareAmount) external nonReentrant returns (uint256 assetsReturned) {
        require(shareAmount > 0, "Vault: zero shares");
        require(shares[msg.sender] >= shareAmount, "Vault: insufficient shares");

        uint256 sharesBefore = totalShares;
        uint256 accounted = internalAssets();
        assetsReturned = (shareAmount * accounted) / sharesBefore;

        uint256 vaultBalance = asset.balanceOf(address(this));
        if (vaultBalance > accounted) {
            uint256 deviation = ((vaultBalance - accounted) * 10_000) / accounted;
            require(deviation <= MAX_PRICE_DEVIATION_BPS, "Vault: price deviation exceeds 5%");
        }

        require(assetsReturned <= vaultBalance, "Vault: insufficient vault balance");

        uint256 depBurn = (totalDeposited * shareAmount) / sharesBefore;
        uint256 retBurn = (strategyReturns * shareAmount) / sharesBefore;
        totalDeposited -= depBurn;
        strategyReturns -= retBurn;

        shares[msg.sender] -= shareAmount;
        totalShares -= shareAmount;

        asset.safeTransfer(msg.sender, assetsReturned);
        emit Withdraw(msg.sender, assetsReturned, shareAmount);
    }

    /// @notice Add a new yield strategy.
    function addStrategy(address target) external onlyOwner {
        require(target != address(0), "Vault: zero strategy address");
        strategies.push(Strategy({target: target, allocated: 0, active: true}));
        emit StrategyAdded(strategies.length - 1, target);
    }

    /// @notice Allocate vault funds to a strategy.
    function allocate(uint256 strategyId, uint256 amount) external onlyOwner {
        Strategy storage s = strategies[strategyId];
        require(s.active, "Vault: strategy inactive");
        require(s.target != address(0), "Vault: strategy zero address");
        require(asset.balanceOf(address(this)) >= amount, "Vault: insufficient balance");

        s.allocated += amount;
        asset.safeTransfer(s.target, amount);
        emit StrategyAllocated(strategyId, amount);
    }

    /// @notice Record yield returned from strategies into internal accounting.
    function reportReturns(uint256 amount) external onlyOwner {
        require(amount > 0, "Vault: zero returns");
        asset.safeTransferFrom(msg.sender, address(this), amount);
        strategyReturns += amount;
        emit StrategyReturnsReported(amount);
    }

    /// @notice Deactivate a strategy.
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

    /// @notice Preview shares for a given deposit amount (uses internal accounting).
    function previewDeposit(uint256 amount) external view returns (uint256) {
        uint256 accounted = internalAssets();
        if (totalShares == 0) return amount;
        return (amount * totalShares) / accounted;
    }
}
