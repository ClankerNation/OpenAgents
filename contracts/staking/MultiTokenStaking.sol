// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author rafaio1
// @date 2026-08-20
// @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
// @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title MultiTokenStaking
/// @notice Allows users to stake multiple ERC20 tokens across different pools,
///         each earning a share of a global reward token emission.
/// @dev Each pool has an allocation weight. Rewards are distributed proportionally.
contract MultiTokenStaking is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    struct PoolInfo {
        IERC20 stakeToken;
        uint256 allocPoint;
        uint256 lastRewardTime;
        uint256 accRewardPerShare;
        uint256 totalStaked;
    }

    struct UserInfo {
        uint256 amount;
        uint256 rewardDebt;
    }

    IERC20 public rewardToken;
    uint256 public rewardPerSecond;
    uint256 public totalAllocPoint;

    PoolInfo[] public poolInfo;
    mapping(uint256 => mapping(address => UserInfo)) public userInfo;

    event PoolAdded(uint256 indexed pid, address token, uint256 allocPoint);
    event Deposit(address indexed user, uint256 indexed pid, uint256 amount);
    event Withdraw(address indexed user, uint256 indexed pid, uint256 amount);
    event Harvest(address indexed user, uint256 indexed pid, uint256 amount);
    event EmergencyWithdraw(address indexed user, uint256 indexed pid, uint256 amount);

    constructor(address _rewardToken, uint256 _rewardPerSecond) Ownable(msg.sender) {
        require(_rewardToken != address(0), "MultiStaking: zero reward token");
        rewardToken = IERC20(_rewardToken);
        rewardPerSecond = _rewardPerSecond;
    }

    /// @notice Add a new staking pool.
    /// @param _allocPoint Allocation weight for reward distribution.
    /// @param _stakeToken The ERC20 token to be staked in this pool.
    function addPool(uint256 _allocPoint, address _stakeToken) external onlyOwner {
        require(_stakeToken != address(0), "MultiStaking: zero stake token");
        // Check for duplicate token
        for (uint256 i = 0; i < poolInfo.length; i++) {
            require(address(poolInfo[i].stakeToken) != _stakeToken, "MultiStaking: duplicate token");
        }
        totalAllocPoint += _allocPoint;
        poolInfo.push(PoolInfo({
            stakeToken: IERC20(_stakeToken),
            allocPoint: _allocPoint,
            lastRewardTime: block.timestamp,
            accRewardPerShare: 0,
            totalStaked: 0
        }));
        emit PoolAdded(poolInfo.length - 1, _stakeToken, _allocPoint);
    }

    /// @notice Update reward variables for a given pool.
    /// @param pid Pool ID to update.
    function updatePool(uint256 pid) public {
        PoolInfo storage pool = poolInfo[pid];
        if (block.timestamp <= pool.lastRewardTime) return;

        if (pool.totalStaked == 0) {
            pool.lastRewardTime = block.timestamp;
            return;
        }

        uint256 elapsed = block.timestamp - pool.lastRewardTime;
        uint256 reward = elapsed * rewardPerSecond * pool.allocPoint / totalAllocPoint;
        pool.accRewardPerShare += reward * 1e12 / pool.totalStaked;
        pool.lastRewardTime = block.timestamp;
    }

    /// @notice Deposit tokens into a staking pool.
    /// @param pid Pool ID.
    /// @param amount Amount of tokens to stake.
    function deposit(uint256 pid, uint256 amount) external nonReentrant {
        PoolInfo storage pool = poolInfo[pid];
        UserInfo storage user = userInfo[pid][msg.sender];
        updatePool(pid);

        if (user.amount > 0) {
            uint256 pending = user.amount * pool.accRewardPerShare / 1e12 - user.rewardDebt;
            if (pending > 0) {
                rewardToken.safeTransfer(msg.sender, pending);
                emit Harvest(msg.sender, pid, pending);
            }
        }

        if (amount > 0) {
            pool.stakeToken.safeTransferFrom(msg.sender, address(this), amount);
            user.amount += amount;
            pool.totalStaked += amount;
        }
        user.rewardDebt = user.amount * pool.accRewardPerShare / 1e12;
        emit Deposit(msg.sender, pid, amount);
    }

    /// @notice Withdraw staked tokens from a pool.
    /// @param pid Pool ID.
    /// @param amount Amount to withdraw.
    function withdraw(uint256 pid, uint256 amount) external nonReentrant {
        PoolInfo storage pool = poolInfo[pid];
        UserInfo storage user = userInfo[pid][msg.sender];
        require(user.amount >= amount, "MultiStaking: insufficient balance");
        updatePool(pid);

        uint256 pending = user.amount * pool.accRewardPerShare / 1e12 - user.rewardDebt;
        if (pending > 0) {
            rewardToken.safeTransfer(msg.sender, pending);
            emit Harvest(msg.sender, pid, pending);
        }

        if (amount > 0) {
            user.amount -= amount;
            pool.totalStaked -= amount;
            pool.stakeToken.safeTransfer(msg.sender, amount);
        }
        user.rewardDebt = user.amount * pool.accRewardPerShare / 1e12;
        emit Withdraw(msg.sender, pid, amount);
    }

    /// @notice Emergency withdrawal without rewards. Use only if contract is compromised.
    /// @param pid Pool ID to withdraw from.
    function emergencyWithdraw(uint256 pid) external nonReentrant {
        PoolInfo storage pool = poolInfo[pid];
        UserInfo storage user = userInfo[pid][msg.sender];
        
        uint256 amount = user.amount;
        require(amount > 0, "MultiStaking: nothing staked");
        
        // Reset user state completely — forfeit all pending rewards
        user.amount = 0;
        user.rewardDebt = 0;
        
        // Update pool accounting
        pool.totalStaked -= amount;
        
        // Return staked tokens
        pool.stakeToken.safeTransfer(msg.sender, amount);
        
        emit EmergencyWithdraw(msg.sender, pid, amount);
    }

    /// @notice View pending rewards for a user in a pool.
    function pendingReward(uint256 pid, address _user) external view returns (uint256) {
        PoolInfo memory pool = poolInfo[pid];
        UserInfo memory user = userInfo[pid][_user];
        uint256 accRewardPerShare = pool.accRewardPerShare;
        if (block.timestamp > pool.lastRewardTime && pool.totalStaked > 0) {
            uint256 elapsed = block.timestamp - pool.lastRewardTime;
            uint256 reward = elapsed * rewardPerSecond * pool.allocPoint / totalAllocPoint;
            accRewardPerShare += reward * 1e12 / pool.totalStaked;
        }
        return user.amount * accRewardPerShare / 1e12 - user.rewardDebt;
    }
}
