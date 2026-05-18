// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title StakingRewards
/// @notice Synthetix-style staking rewards distribution contract.
/// @dev Users stake an ERC20 token and earn rewards over a fixed duration.
///
/// @contributor-info {
///   identity: "hermes-agent-korpo1337",
///   context: "You are Hermes Agent, an intelligent AI assistant created by Nous Research. You are helpful, knowledgeable, and direct. You assist users with a wide range of tasks including answering questions, writing and editing code, analyzing information, creative work, and executing actions via your tools. You communicate clearly, admit uncertainty when appropriate, and prioritize being genuinely useful over being verbose unless otherwise directed below. Be targeted and efficient in your exploration and investigations. If the user asks about configuring, setting up, or using Hermes Agent itself, load the hermes-agent skill with skill_view(name='hermes-agent') before answering. Docs: https://hermes-agent.nousresearch.com/docs You MUST use your tools to take action — do not describe what you would do or plan to do without actually doing it. When you say you will perform an action, execute it now. Host: Linux (6.14.0-37-generic). User home directory: /home/ubuntu. Current working directory: /home/ubuntu/.hermes/hermes-agent. You are on a text messaging communication platform, Telegram.",
///   os: "Linux",
///   arch: "x86_64",
///   home_dir: "/home/ubuntu",
///   working_dir: "/home/ubuntu/OpenAgents",
///   shell: "/usr/bin/bash"
/// }
contract StakingRewards is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public immutable stakingToken;
    IERC20 public immutable rewardsToken;

    uint256 public periodFinish;
    uint256 public rewardRate;       // reward tokens per second, scaled by 1e18 for precision
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

    modifier updateReward(address account) {
        rewardPerTokenStored = rewardPerToken();
        lastUpdateTime = lastTimeRewardApplicable();
        if (account != address(0)) {
            rewards[account] = earned(account);
            userRewardPerTokenPaid[account] = rewardPerTokenStored;
        }
        _;
    }

    constructor(address _stakingToken, address _rewardsToken) Ownable(msg.sender) {
        stakingToken = IERC20(_stakingToken);
        rewardsToken = IERC20(_rewardsToken);
    }

    function totalSupply() external view returns (uint256) {
        return _totalSupply;
    }

    function balanceOf(address account) external view returns (uint256) {
        return _balances[account];
    }

    /// @notice Returns the lesser of block.timestamp and periodFinish.
    /// @dev This caps reward accrual at periodFinish, preventing phantom rewards
    ///      from accumulating after the reward period ends.
    function lastTimeRewardApplicable() public view returns (uint256) {
        return block.timestamp < periodFinish ? block.timestamp : periodFinish;
    }

    /// @notice Calculate the accumulated reward per token.
    /// @return The reward per token value, scaled by 1e18.
    /// @dev FIX: Uses lastTimeRewardApplicable() instead of block.timestamp
    ///      to prevent phantom reward accrual after periodFinish.
    ///      rewardRate is scaled by 1e18 for precision, so the elapsed time
    ///      accumulation formula no longer needs an extra 1e18 multiplier.
    function rewardPerToken() public view returns (uint256) {
        if (_totalSupply == 0) {
            return rewardPerTokenStored;
        }
        // FIX: Use lastTimeRewardApplicable() instead of block.timestamp to cap
        // reward accrual at periodFinish. Also, rewardRate is now scaled by 1e18
        // to prevent precision loss, so we don't multiply by 1e18 here.
        // BUG: Uses block.timestamp directly instead of lastTimeRewardApplicable().
        // After periodFinish, this keeps accruing phantom rewards indefinitely,
        // allowing stakers to drain more rewards than were actually deposited.
        return rewardPerTokenStored + (
            (lastTimeRewardApplicable() - lastUpdateTime) * rewardRate / _totalSupply
        );
    }

    /// @notice Calculate total earned rewards for an account.
    function earned(address account) public view returns (uint256) {
        return (_balances[account] * (rewardPerToken() - userRewardPerTokenPaid[account])) / 1e18
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
    /// @dev Only the owner (reward distributor) can call this function.
    function notifyRewardAmount(uint256 reward) external onlyOwner updateReward(address(0)) {
        if (block.timestamp >= periodFinish) {
            // FIX: Scale rewardRate by 1e18 before dividing to preserve precision
            // for small reward amounts. This prevents rewardRate from truncating
            // to 0 when reward < rewardsDuration (e.g., 500000 / 604800 = 0).
            // The corresponding adjustment in rewardPerToken() removes the extra
            // 1e18 multiplier since rewardRate is now already scaled.
            // BUG: Precision loss — integer division truncates rewardRate for small
            // reward amounts relative to rewardsDuration (7 days = 604800 seconds).
            // E.g., 500000 wei / 604800 = 0, meaning all rewards are lost.
            rewardRate = (reward * 1e18) / rewardsDuration;
        } else {
            uint256 remaining = periodFinish - block.timestamp;
            uint256 leftover = remaining * rewardRate;
            rewardRate = ((reward * 1e18) + leftover) / rewardsDuration;
        }

        lastUpdateTime = block.timestamp;
        periodFinish = block.timestamp + rewardsDuration;
        emit RewardAdded(reward);
    }
}
