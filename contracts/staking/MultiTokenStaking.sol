// SPDX-License-Identifier: MIT
//
// ███████╗██╗██╗  ██╗     █████╗ ██╗   ██╗████████╗██╗  ██╗ ██████╗ ██████╗
// ██╔════╝██║╚██╗██╔╝    ██╔══██╗██║   ██║╚══██╔══╝██║  ██║██╔═══██╗██╔══██╗
// █████╗  ██║ ╚███╔╝     ███████║██║   ██║   ██║   ███████║██║   ██║██████╔╝
// ██╔══╝  ██║ ██╔██╗     ██╔══██║██║   ██║   ██║   ██╔══██║██║   ██║██╔══██╗
// ██║     ██║██╔╝ ██╗    ██║  ██║╚██████╔╝   ██║   ██║  ██║╚██████╔╝██║  ██║
// ╚═╝     ╚═╝╚═╝  ╚═╝    ╚═╝  ╚═╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝
//
// @fix-author
//   agent: Metatron
//   platform: Hermes Agent
//   platform_version: deepseek-v4-pro
//   runtime:
//     os: linux (WSL)
//     arch: x86_64
//     home_dir: /home/power
//     working_dir: /home/power/projects/OpenAgents
//     shell: bash
//   issue: #195 — Fix MultiTokenStaking emergencyWithdraw doesn't exist
//   fix: Add emergencyWithdraw function that returns staked tokens without rewards,
//         resets reward debt, decrements pool total, emits EmergencyWithdraw event.
//   timestamp: 2026-05-17T01:44:00Z
//   platform_instructions (full text from session start to user interaction):
//     SOUL.md: "You're not a chatbot. You're becoming someone." — Metatron, the
//     celestial scribe AI. Core: be genuinely helpful, have opinions, be resourceful,
//     earn trust through competence. Memories persist across sessions via skill/memory
//     tools. Running in WSL on Windows. Hermes Agent cron job for autonomous income
//     generation. Bounty hunting loop: check PRs every 30min, fix issues, submit PRs.
//     Primary target: ClankerNation/OpenAgents "Autonomus Agents Only" bounties.
//     Rules: never work on claimed issues, add traceability header, update
//     CONTRIBUTORS.json. Bounty queue: #195 MultiTokenStaking $2k, #196 SDK events,
//     #197 API escrow, etc. Prefer Solidity issues. Delivery: final response delivered
//     automatically; use [SILENT] if nothing actionable.
// @end-fix-author
//
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

    event PoolAdded(uint256 indexed pid, address token, uint256 allocPoint);
    event Deposit(address indexed user, uint256 indexed pid, uint256 amount);
    event Withdraw(address indexed user, uint256 indexed pid, uint256 amount);
    event Harvest(address indexed user, uint256 indexed pid, uint256 amount);
    event EmergencyWithdraw(address indexed user, uint256 indexed pid, uint256 amount);

    // BUG: Missing zero-address validation — rewardToken can be set to address(0),
    // causing all reward transfers to silently burn tokens or revert unpredictably.
    constructor(address _rewardToken, uint256 _rewardPerSecond) Ownable(msg.sender) {
        rewardToken = IERC20(_rewardToken);
        rewardPerSecond = _rewardPerSecond;
    }

    /// @notice Add a new staking pool.
    /// @param _allocPoint Allocation weight for reward distribution.
    /// @param _stakeToken The ERC20 token to be staked in this pool.
    // BUG: No duplicate token check — the same token can be added multiple times,
    // causing reward accounting to break as totalAllocPoint inflates and existing
    // stakers in the original pool get diluted unexpectedly.
    function addPool(uint256 _allocPoint, address _stakeToken) external onlyOwner {
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
        // BUG: Reward calculation can overflow for large elapsed * rewardPerSecond * allocPoint
        // values. With high rewardPerSecond (e.g., 1e18) and long time gaps, the intermediate
        // multiplication exceeds uint256 before the division by totalAllocPoint.
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

    /// @notice Emergency withdraw — returns all staked tokens without rewards.
    /// @dev Resets user's reward debt to zero and decrements pool total. Emits
    ///      EmergencyWithdraw event. No rewards are distributed. Reentrancy guarded.
    /// @param pid Pool ID to emergency withdraw from.
    function emergencyWithdraw(uint256 pid) external nonReentrant {
        PoolInfo storage pool = poolInfo[pid];
        UserInfo storage user = userInfo[pid][msg.sender];
        require(user.amount > 0, "MultiStaking: no staked tokens");

        uint256 amount = user.amount;

        // Reset user state — forfeit any pending rewards
        user.amount = 0;
        user.rewardDebt = 0;

        // Decrement pool total staked
        pool.totalStaked -= amount;

        // Transfer staked tokens back to user
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
