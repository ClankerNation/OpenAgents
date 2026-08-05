// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @custom:contributor-info
///   agent: Codex
///   public_task: OpenAgents issue #7, cap reward accrual and restrict reward notification
///   runtime: macOS Darwin arm64, zsh, /tmp/openagents-issue7.ZO0M1e/repo
///   privacy: private system/developer/session initialization text intentionally omitted

/// @title StakingRewards
/// @notice Synthetix-style staking rewards distribution contract.
/// @dev Users stake an ERC20 token and earn rewards over a fixed duration.
contract StakingRewards is ReentrancyGuard {
    using SafeERC20 for IERC20;

    uint256 private constant RATE_PRECISION = 1e18;
    uint256 private constant REWARD_PER_TOKEN_PRECISION = 1e27;

    IERC20 public immutable stakingToken;
    IERC20 public immutable rewardsToken;
    address public owner;
    address public rewardsDistributor;

    uint256 public periodFinish;
    // Scaled by RATE_PRECISION to preserve sub-wei-per-second reward rates.
    uint256 public rewardRate;
    uint256 public rewardsDuration = 7 days;
    uint256 public lastUpdateTime;
    uint256 public rewardPerTokenStored;

    mapping(address => uint256) public userRewardPerTokenPaid;
    mapping(address => uint256) public rewards;

    uint256 private _totalSupply;
    mapping(address => uint256) private _balances;

    event Staked(address indexed user, uint256 amount);
    event Withdrawn(address indexed user, uint256 amount);
    event RewardPaid(address indexed user, uint256 reward);
    event RewardAdded(uint256 reward);
    event RewardsDistributorUpdated(address indexed distributor);

    modifier updateReward(address account) {
        rewardPerTokenStored = rewardPerToken();
        lastUpdateTime = lastTimeRewardApplicable();
        if (account != address(0)) {
            rewards[account] = earned(account);
            userRewardPerTokenPaid[account] = rewardPerTokenStored;
        }
        _;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "StakingRewards: not owner");
        _;
    }

    modifier onlyRewardsDistributor() {
        require(msg.sender == rewardsDistributor, "StakingRewards: not distributor");
        _;
    }

    constructor(address _stakingToken, address _rewardsToken) {
        stakingToken = IERC20(_stakingToken);
        rewardsToken = IERC20(_rewardsToken);
        owner = msg.sender;
        rewardsDistributor = msg.sender;
    }

    function totalSupply() external view returns (uint256) {
        return _totalSupply;
    }

    function balanceOf(address account) external view returns (uint256) {
        return _balances[account];
    }

    function lastTimeRewardApplicable() public view returns (uint256) {
        return block.timestamp < periodFinish ? block.timestamp : periodFinish;
    }

    /// @notice Calculate the accumulated reward per token.
    /// @return The reward per token value.
    function rewardPerToken() public view returns (uint256) {
        if (_totalSupply == 0) {
            return rewardPerTokenStored;
        }
        uint256 applicableTime = lastTimeRewardApplicable();
        if (applicableTime <= lastUpdateTime) {
            return rewardPerTokenStored;
        }
        return rewardPerTokenStored + (
            (applicableTime - lastUpdateTime) * rewardRate * REWARD_PER_TOKEN_PRECISION / RATE_PRECISION / _totalSupply
        );
    }

    /// @notice Calculate total earned rewards for an account.
    function earned(address account) public view returns (uint256) {
        return (_balances[account] * (rewardPerToken() - userRewardPerTokenPaid[account])) / REWARD_PER_TOKEN_PRECISION
            + rewards[account];
    }

    /// @notice Stake tokens to earn rewards.
    /// @param amount Amount of staking token to deposit.
    function stake(uint256 amount) external nonReentrant updateReward(msg.sender) {
        require(amount > 0, "Cannot stake 0");
        _totalSupply += amount;
        _balances[msg.sender] += amount;
        stakingToken.safeTransferFrom(msg.sender, address(this), amount);
        emit Staked(msg.sender, amount);
    }

    /// @notice Withdraw staked tokens.
    /// @param amount Amount to withdraw.
    function withdraw(uint256 amount) external nonReentrant updateReward(msg.sender) {
        require(amount > 0, "Cannot withdraw 0");
        _totalSupply -= amount;
        _balances[msg.sender] -= amount;
        stakingToken.safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount);
    }

    /// @notice Claim accumulated rewards.
    function getReward() external nonReentrant updateReward(msg.sender) {
        uint256 reward = rewards[msg.sender];
        if (reward > 0) {
            rewards[msg.sender] = 0;
            rewardsToken.safeTransfer(msg.sender, reward);
            emit RewardPaid(msg.sender, reward);
        }
    }

    /// @notice Notify the contract of a new reward amount to distribute.
    /// @param reward Total reward tokens to distribute over the duration.
    function notifyRewardAmount(uint256 reward) external onlyRewardsDistributor updateReward(address(0)) {
        uint256 totalReward = reward;

        if (block.timestamp >= periodFinish) {
            rewardRate = (totalReward * RATE_PRECISION) / rewardsDuration;
        } else {
            uint256 remaining = periodFinish - block.timestamp;
            uint256 leftover = (remaining * rewardRate) / RATE_PRECISION;
            totalReward += leftover;
            rewardRate = (totalReward * RATE_PRECISION) / rewardsDuration;
        }

        lastUpdateTime = block.timestamp;
        periodFinish = block.timestamp + rewardsDuration;
        emit RewardAdded(reward);
    }

    function setRewardsDistributor(address distributor) external onlyOwner {
        require(distributor != address(0), "StakingRewards: zero distributor");
        rewardsDistributor = distributor;
        emit RewardsDistributorUpdated(distributor);
    }
}
