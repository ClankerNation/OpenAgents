// SPDX-License-Identifier: MIT
// YieldVault.sol — Phantom reward fix
// Issue #66: Fix rewardPerToken to cap at periodFinish, add access control to
// notifyRewardAmount, and prevent precision loss in rewardRate calculation.
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title YieldVault
/// @notice Vault that distributes rewards proportionally to depositors over a fixed duration.
/// @dev Users deposit a base token and earn rewards based on their share of total deposits.
///      Rewards are distributed linearly over `rewardsDuration` and must be claimed manually.
contract YieldVault is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public immutable baseToken;
    IERC20 public immutable rewardToken;

    uint256 public periodFinish;
    uint256 public rewardRate;
    uint256 public rewardsDuration = 7 days;
    uint256 public lastUpdateTime;
    uint256 public rewardPerTokenStored;

    uint256 public totalDeposits;
    mapping(address => uint256) public userDeposits;
    mapping(address => uint256) public userRewardPerTokenPaid;
    mapping(address => uint256) public rewards;

    event Deposited(address indexed user, uint256 amount);
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

    constructor(address _baseToken, address _rewardToken) Ownable(msg.sender) {
        baseToken = IERC20(_baseToken);
        rewardToken = IERC20(_rewardToken);
    }

    function lastTimeRewardApplicable() public view returns (uint256) {
        return block.timestamp < periodFinish ? block.timestamp : periodFinish;
    }

    function rewardPerToken() public view returns (uint256) {
        if (totalDeposits == 0) {
            return rewardPerTokenStored;
        }
        // Uses lastTimeRewardApplicable() — caps at periodFinish to prevent phantom rewards.
        return rewardPerTokenStored + (
            (lastTimeRewardApplicable() - lastUpdateTime) * rewardRate * 1e18 / totalDeposits
        );
    }

    function earned(address account) public view returns (uint256) {
        return (userDeposits[account] * (rewardPerToken() - userRewardPerTokenPaid[account])) / 1e18
            + rewards[account];
    }

    function deposit(uint256 amount) external nonReentrant updateReward(msg.sender) {
        require(amount > 0, "Vault: zero deposit");
        totalDeposits += amount;
        userDeposits[msg.sender] += amount;
        baseToken.safeTransferFrom(msg.sender, address(this), amount);
        emit Deposited(msg.sender, amount);
    }

    function withdraw(uint256 amount) external nonReentrant updateReward(msg.sender) {
        require(amount > 0, "Vault: zero withdraw");
        require(userDeposits[msg.sender] >= amount, "Vault: insufficient balance");
        totalDeposits -= amount;
        userDeposits[msg.sender] -= amount;
        baseToken.safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount);
    }

    function getReward() external nonReentrant updateReward(msg.sender) {
        uint256 reward = rewards[msg.sender];
        if (reward > 0) {
            rewards[msg.sender] = 0;
            rewardToken.safeTransfer(msg.sender, reward);
            emit RewardPaid(msg.sender, reward);
        }
    }

    // Access control: only owner can add rewards.
    function notifyRewardAmount(uint256 reward) external onlyOwner updateReward(address(0)) {
        if (block.timestamp >= periodFinish) {
            // Uses scaled reward calculation (1e18 precision) to prevent precision loss
            // for small reward amounts relative to duration.
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

    function setRewardsDuration(uint256 _rewardsDuration) external onlyOwner {
        require(block.timestamp > periodFinish, "Vault: rewards period active");
        rewardsDuration = _rewardsDuration;
    }
}
