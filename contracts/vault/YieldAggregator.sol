// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor rafaio1
 * @timestamp 2026-08-20T02:15:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */


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
    event Rebalanced(uint256 indexed strategyId, uint256 oldAllocation, uint256 newAllocation);

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

    /// @notice Add a new yield strategy.
    /// @param target Address of the strategy contract.
    // BUG: Strategy target can be zero address — allocating funds to address(0)
    // would burn them permanently via the external call.
    /// @notice Add a new yield strategy with allocation cap.
    /// @param target Address of the strategy contract.
    /// @param maxAllocationBps Maximum allocation percentage in basis points (e.g., 3000 = 30%).
    function addStrategy(address target, uint256 maxAllocationBps) external onlyOwner {
        require(target != address(0), "Vault: zero address");
        require(maxAllocationBps <= 10000, "Vault: invalid bps");
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
    /// @notice Allocate vault funds to a strategy respecting allocation caps.
    /// @param strategyId Index of the strategy.
    /// @param amount Amount to allocate.
    function allocate(uint256 strategyId, uint256 amount) external onlyOwner {
        Strategy storage s = strategies[strategyId];
        require(s.active, "Vault: strategy inactive");
        require(asset.balanceOf(address(this)) >= amount, "Vault: insufficient balance");

        // Enforce max allocation cap
        uint256 total = totalAssets();
        if (total > 0) {
            uint256 newAllocated = s.allocated + amount;
            uint256 maxAllowed = (total * s.maxAllocationBps) / 10000;
            require(newAllocated <= maxAllowed, "Vault: exceeds allocation cap");
        }

        s.allocated += amount;
        asset.safeTransfer(s.target, amount);
        emit StrategyAllocated(strategyId, amount);
    }

    /// @notice Rebalance allocations across all active strategies proportionally.
    /// @dev Redistributes vault balance according to each strategy's maxAllocationBps weight.
    function rebalance() external onlyOwner nonReentrant {
        uint256 total = totalAssets();
        if (total == 0) return;

        // Calculate total weight of active strategies
        uint256 totalWeight = 0;
        for (uint256 i = 0; i < strategies.length; i++) {
            if (strategies[i].active) {
                totalWeight += strategies[i].maxAllocationBps;
            }
        }
        require(totalWeight > 0, "Vault: no active strategies");

        // Pull all allocated funds back to vault first
        for (uint256 i = 0; i < strategies.length; i++) {
            if (strategies[i].active && strategies[i].allocated > 0) {
                // In production, this would call strategy.withdraw()
                // For this implementation, we track accounting and assume funds are returned
                // Real implementation needs IStrategy interface
            }
        }

        // Redistribute according to weights
        uint256 vaultBalance = asset.balanceOf(address(this));
        uint256 distributed = 0;
        for (uint256 i = 0; i < strategies.length; i++) {
            Strategy storage s = strategies[i];
            if (!s.active) continue;

            uint256 targetAlloc = (vaultBalance * s.maxAllocationBps) / totalWeight;
            uint256 oldAlloc = s.allocated;

            if (targetAlloc > oldAlloc) {
                uint256 toSend = targetAlloc - oldAlloc;
                if (distributed + toSend <= vaultBalance) {
                    asset.safeTransfer(s.target, toSend);
                    s.allocated = targetAlloc;
                    distributed += toSend;
                }
            } else if (targetAlloc < oldAlloc) {
                s.allocated = targetAlloc;
            }

            emit Rebalanced(i, oldAlloc, s.allocated);
        }
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

    // Timelock ownership transfer
    address private _pendingOwner;
    uint256 private _ownershipTransferDeadline;
    uint256 public constant OWNERSHIP_TIMELOCK = 2 days;

    event OwnershipTransferStarted(address indexed previousOwner, address indexed newOwner, uint256 deadline);
    event OwnershipTransferAccepted(address indexed previousOwner, address indexed newOwner);
    event OwnershipTransferCancelled(address indexed previousOwner, address indexed cancelledOwner);

    /// @notice Start ownership transfer with 2-day timelock.
    /// @param newOwner Address of the pending owner.
    function transferOwnership(address newOwner) public override onlyOwner {
        require(newOwner != address(0), "Ownable: zero address");
        require(newOwner != owner(), "Ownable: same owner");
        _pendingOwner = newOwner;
        _ownershipTransferDeadline = block.timestamp + OWNERSHIP_TIMELOCK;
        emit OwnershipTransferStarted(owner(), newOwner, _ownershipTransferDeadline);
    }

    /// @notice Accept ownership after timelock period.
    function acceptOwnership() external {
        require(msg.sender == _pendingOwner, "Ownable: not pending owner");
        require(block.timestamp >= _ownershipTransferDeadline, "Ownable: timelock active");
        
        address oldOwner = owner();
        _transferOwnership(_pendingOwner);
        _pendingOwner = address(0);
        _ownershipTransferDeadline = 0;
        emit OwnershipTransferAccepted(oldOwner, msg.sender);
    }

    /// @notice Cancel pending ownership transfer.
    function cancelOwnershipTransfer() external onlyOwner {
        require(_pendingOwner != address(0), "Ownable: no pending transfer");
        address cancelled = _pendingOwner;
        _pendingOwner = address(0);
        _ownershipTransferDeadline = 0;
        emit OwnershipTransferCancelled(owner(), cancelled);
    }

    /// @notice Get pending owner address.
    function pendingOwner() external view returns (address) {
        return _pendingOwner;
    }

    /// @notice Get ownership transfer deadline.
    function ownershipTransferDeadline() external view returns (uint256) {
        return _ownershipTransferDeadline;
    }

}
