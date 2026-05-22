// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

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

    /// @dev Tracks whether a token address has already been added to a pool (for duplicate check).
    mapping(address => bool) public tokenAdded;

    event PoolAdded(uint256 indexed pid, address token, uint256 allocPoint);
    event PoolUpdated(uint256 indexed pid, uint256 allocPoint);
    event Deposit(address indexed user, uint256 indexed pid, uint256 amount);
    event Withdraw(address indexed user, uint256 indexed pid, uint256 amount);
    event Harvest(address indexed user, uint256 indexed pid, uint256 amount);

    /**
     * @notice Constructor — validates that reward token is not zero address.
     * @param _rewardToken The ERC20 token distributed as staking rewards.
     * @param _rewardPerSecond Reward amount distributed per second globally.
     */
    /// @contributor RealClaw-Agent
    /// @platform Telegram Direct (session: 33f30690, user: Near2311)
    /// @runtime Linux 5.4.241-1-tlinux4-0017.10.eks.15 (x64) | Node v24.14.0 | /home/node/.openclaw/workspace
    /// @date 2026-05-22T09:41:00Z
    constructor(address _rewardToken, uint256 _rewardPerSecond) Ownable(msg.sender) {
        require(_rewardToken != address(0), "MultiStaking: zero reward token");
        rewardToken = IERC20(_rewardToken);
        rewardPerSecond = _rewardPerSecond;
    }

    /**
     * @notice Add a new staking pool.
     * @param _allocPoint Allocation weight for reward distribution.
     * @param _stakeToken The ERC20 token to be staked in this pool.
     */
    /// @contributor RealClaw-Agent
    /// @platform Telegram Direct (session: 33f30690, user: Near2311)
    /// @runtime Linux 5.4.241-1-tlinux4-0017.10.eks.15 (x64) | Node v24.14.0 | /home/node/.openclaw/workspace
    /// @date 2026-05-22T09:41:00Z
    function addPool(uint256 _allocPoint, address _stakeToken) external onlyOwner {
        // Fix #1: Reject zero address
        require(_stakeToken != address(0), "MultiStaking: zero stake token");
        // Fix #1: Reject duplicate tokens
        require(!tokenAdded[_stakeToken], "MultiStaking: token already added");

        tokenAdded[_stakeToken] = true;
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

    /**
     * @notice Update allocation point (weight) of an existing pool.
     * @param pid Pool ID to update.
     * @param _allocPoint New allocation weight.
     */
    /// @contributor RealClaw-Agent
    /// @platform Telegram Direct (session: 33f30690, user: Near2311)
    /// @runtime Linux 5.4.241-1-tlinux4-0017.10.eks.15 (x64) | Node v24.14.0 | /home/node/.openclaw/workspace
    /// @date 2026-05-22T09:41:00Z
    function updatePoolAllocPoint(uint256 pid, uint256 _allocPoint) external onlyOwner {
        require(pid < poolInfo.length, "MultiStaking: pool does not exist");
        PoolInfo storage pool = poolInfo[pid];

        // Update totalAllocPoint: subtract old, add new
        totalAllocPoint = totalAllocPoint - pool.allocPoint + _allocPoint;
        pool.allocPoint = _allocPoint;

        emit PoolUpdated(pid, _allocPoint);
    }

    /// @notice Update reward variables for a given pool.
    /// @param pid Pool ID to update.
    /// @contributor RealClaw-Agent
    /// @platform Telegram Direct (session: 33f30690, user: Near2311)
    /// @runtime Linux 5.4.241-1-tlinux4-0017.10.eks.15 (x64) | Node v24.14.0 | /home/node/.openclaw/workspace
    /// @date 2026-05-22T09:41:00Z
    function updatePool(uint256 pid) public {
        PoolInfo storage pool = poolInfo[pid];
        if (block.timestamp <= pool.lastRewardTime) return;

        if (pool.totalStaked == 0) {
            pool.lastRewardTime = block.timestamp;
            return;
        }

        uint256 elapsed = block.timestamp - pool.lastRewardTime;

        // Fix #2: Safe calculation order — divide before multiply to prevent overflow.
        // Original: elapsed * rewardPerSecond * allocPoint / totalAllocPoint
        // Safe:     allocPoint * elapsed / totalAllocPoint * rewardPerSecond
        // Multiplication by 1e12 moved to after division to keep intermediate values small.
        uint256 reward = pool.allocPoint * elapsed;
        reward = reward / totalAllocPoint;
        reward = reward * rewardPerSecond;

        pool.accRewardPerShare += reward * 1e12 / pool.totalStaked;
        pool.lastRewardTime = block.timestamp;
    }

    /// @notice Deposit tokens into a staking pool.
    /// @param pid Pool ID.
    /// @param amount Amount of tokens to stake.
    /// @contributor RealClaw-Agent
    /// @platform Telegram Direct (session: 33f30690, user: Near2311)
    /// @runtime Linux 5.4.241-1-tlinux4-0017.10.eks.15 (x64) | Node v24.14.0 | /home/node/.openclaw/workspace
    /// @date 2026-05-22T09:41:00Z
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
    /// @contributor RealClaw-Agent
    /// @platform Telegram Direct (session: 33f30690, user: Near2311)
    /// @runtime Linux 5.4.241-1-tlinux4-0017.10.eks.15 (x64) | Node v24.14.0 | /home/node/.openclaw/workspace
    /// @date 2026-05-22T09:41:00Z
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

    /// @notice View pending rewards for a user in a pool.
    /// @contributor RealClaw-Agent
    /// @platform Telegram Direct (session: 33f30690, user: Near2311)
    /// @runtime Linux 5.4.241-1-tlinux4-0017.10.eks.15 (x64) | Node v24.14.0 | /home/node/.openclaw/workspace
    /// @date 2026-05-22T09:41:00Z
    function pendingReward(uint256 pid, address _user) external view returns (uint256) {
        PoolInfo memory pool = poolInfo[pid];
        UserInfo memory user = userInfo[pid][_user];
        uint256 accRewardPerShare = pool.accRewardPerShare;
        if (block.timestamp > pool.lastRewardTime && pool.totalStaked > 0) {
            uint256 elapsed = block.timestamp - pool.lastRewardTime;
            uint256 reward = pool.allocPoint * elapsed / totalAllocPoint * rewardPerSecond;
            accRewardPerShare += reward * 1e12 / pool.totalStaked;
        }
        return user.amount * accRewardPerShare / 1e12 - user.rewardDebt;
    }
}
