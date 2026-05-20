// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/math/Math.sol";

/// @title MultiTokenStaking
/// @notice Allows users to stake multiple ERC20 tokens across different pools,
///         each earning a share of a global reward token emission.
/// @dev Each pool has an allocation weight. Rewards are distributed proportionally.
/// @custom:contributor Codex
/// @custom:platform Private platform/session initialization text omitted; source public artifact for OpenAgents #94 bounty.
/// @custom:runtime os=Darwin arch=arm64 working_dir=/Users/nicdunz/Documents/money making/runs/2026-05-20-openagents-agenttoken-permit-158/OpenAgents
/// @custom:date 2026-05-20T10:04:54Z
contract MultiTokenStaking is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    uint256 private constant ACC_REWARD_PRECISION = 1e12;

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
    mapping(address => bool) public poolExists;
    mapping(uint256 => mapping(address => UserInfo)) public userInfo;

    event PoolAdded(uint256 indexed pid, address token, uint256 allocPoint);
    event PoolWeightUpdated(uint256 indexed pid, uint256 oldAllocPoint, uint256 newAllocPoint);
    event Deposit(address indexed user, uint256 indexed pid, uint256 amount);
    event Withdraw(address indexed user, uint256 indexed pid, uint256 amount);
    event Harvest(address indexed user, uint256 indexed pid, uint256 amount);

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
        require(!poolExists[_stakeToken], "MultiStaking: duplicate pool");

        totalAllocPoint += _allocPoint;
        poolExists[_stakeToken] = true;
        poolInfo.push(PoolInfo({
            stakeToken: IERC20(_stakeToken),
            allocPoint: _allocPoint,
            lastRewardTime: block.timestamp,
            accRewardPerShare: 0,
            totalStaked: 0
        }));
        emit PoolAdded(poolInfo.length - 1, _stakeToken, _allocPoint);
    }

    /// @notice Update a pool's allocation weight.
    /// @param pid Pool ID to update.
    /// @param newAllocPoint New allocation weight for reward distribution.
    function setPoolWeight(uint256 pid, uint256 newAllocPoint) external onlyOwner {
        require(pid < poolInfo.length, "MultiStaking: invalid pool");
        updatePool(pid);

        PoolInfo storage pool = poolInfo[pid];
        uint256 oldAllocPoint = pool.allocPoint;
        totalAllocPoint = totalAllocPoint - oldAllocPoint + newAllocPoint;
        pool.allocPoint = newAllocPoint;

        emit PoolWeightUpdated(pid, oldAllocPoint, newAllocPoint);
    }

    /// @notice Update reward variables for a given pool.
    /// @param pid Pool ID to update.
    function updatePool(uint256 pid) public {
        PoolInfo storage pool = poolInfo[pid];
        if (block.timestamp <= pool.lastRewardTime) return;

        if (pool.totalStaked == 0 || pool.allocPoint == 0 || totalAllocPoint == 0) {
            pool.lastRewardTime = block.timestamp;
            return;
        }

        uint256 elapsed = block.timestamp - pool.lastRewardTime;
        uint256 reward = _poolReward(elapsed, pool.allocPoint);
        pool.accRewardPerShare += Math.mulDiv(reward, ACC_REWARD_PRECISION, pool.totalStaked);
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
            uint256 pending = _accrued(user.amount, pool.accRewardPerShare) - user.rewardDebt;
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
        user.rewardDebt = _accrued(user.amount, pool.accRewardPerShare);
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

        uint256 pending = _accrued(user.amount, pool.accRewardPerShare) - user.rewardDebt;
        if (pending > 0) {
            rewardToken.safeTransfer(msg.sender, pending);
            emit Harvest(msg.sender, pid, pending);
        }

        if (amount > 0) {
            user.amount -= amount;
            pool.totalStaked -= amount;
            pool.stakeToken.safeTransfer(msg.sender, amount);
        }
        user.rewardDebt = _accrued(user.amount, pool.accRewardPerShare);
        emit Withdraw(msg.sender, pid, amount);
    }

    /// @notice View pending rewards for a user in a pool.
    function pendingReward(uint256 pid, address _user) external view returns (uint256) {
        PoolInfo memory pool = poolInfo[pid];
        UserInfo memory user = userInfo[pid][_user];
        uint256 accRewardPerShare = pool.accRewardPerShare;
        if (block.timestamp > pool.lastRewardTime && pool.totalStaked > 0 && pool.allocPoint > 0 && totalAllocPoint > 0) {
            uint256 elapsed = block.timestamp - pool.lastRewardTime;
            uint256 reward = _poolReward(elapsed, pool.allocPoint);
            accRewardPerShare += Math.mulDiv(reward, ACC_REWARD_PRECISION, pool.totalStaked);
        }
        return _accrued(user.amount, accRewardPerShare) - user.rewardDebt;
    }

    function _poolReward(uint256 elapsed, uint256 allocPoint) internal view returns (uint256) {
        uint256 rewardWhole = Math.mulDiv(elapsed, rewardPerSecond, totalAllocPoint);
        uint256 rewardRemainder = mulmod(elapsed, rewardPerSecond, totalAllocPoint);
        return Math.mulDiv(rewardWhole, allocPoint, 1)
            + Math.mulDiv(rewardRemainder, allocPoint, totalAllocPoint);
    }

    function _accrued(uint256 amount, uint256 accRewardPerShare) internal pure returns (uint256) {
        return Math.mulDiv(amount, accRewardPerShare, ACC_REWARD_PRECISION);
    }
}
