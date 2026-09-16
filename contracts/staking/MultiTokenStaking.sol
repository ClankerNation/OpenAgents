// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title MultiTokenStaking
 * @notice Staking contract supporting multiple token pools with reward distribution
 */
contract MultiTokenStaking is Ownable {
    struct Pool {
        IERC20 token;
        uint256 totalStaked;
        uint256 rewardRate;
        uint256 lastUpdateTime;
        uint256 rewardPerTokenStored;
        bool active;
    }

    struct UserStake {
        uint256 amount;
        uint256 rewardDebt;
    }

    IERC20 public rewardToken;
    Pool[] public pools;
    mapping(uint256 => mapping(address => UserStake)) public userStakes;
    mapping(address => uint256) public totalUserStakes;

    event Stake(address indexed user, uint256 indexed poolId, uint256 amount);
    event Withdraw(address indexed user, uint256 indexed poolId, uint256 amount);
    event RewardClaimed(address indexed user, uint256 indexed poolId, uint256 amount);
    event EmergencyWithdraw(address indexed user, uint256 indexed poolId, uint256 amount);
    event PoolCreated(uint256 indexed poolId, address token, uint256 rewardRate);
    event PoolUpdated(uint256 indexed poolId, uint256 rewardRate);

    constructor(IERC20 _rewardToken) Ownable(msg.sender) {
        rewardToken = _rewardToken;
    }

    function createPool(IERC20 token, uint256 rewardRate) external onlyOwner returns (uint256) {
        require(pools.length < 100, "Max pools reached");
        pools.push(Pool({
            token: token,
            totalStaked: 0,
            rewardRate: rewardRate,
            lastUpdateTime: block.timestamp,
            rewardPerTokenStored: 0,
            active: true
        }));
        emit PoolCreated(pools.length - 1, address(token), rewardRate);
        return pools.length - 1;
    }

    function updatePool(uint256 poolId, uint256 newRewardRate) external onlyOwner {
        require(poolId < pools.length, "Invalid pool");
        _updateReward(poolId);
        pools[poolId].rewardRate = newRewardRate;
        pools[poolId].lastUpdateTime = block.timestamp;
        emit PoolUpdated(poolId, newRewardRate);
    }

    function stake(uint256 poolId, uint256 amount) external {
        require(poolId < pools.length, "Invalid pool");
        require(pools[poolId].active, "Pool inactive");
        require(amount > 0, "Amount must be > 0");

        _updateReward(poolId);

        userStakes[poolId][msg.sender].amount += amount;
        userStakes[poolId][msg.sender].rewardDebt = _getUserRewardDebt(poolId, msg.sender);
        pools[poolId].totalStaked += amount;
        totalUserStakes[msg.sender] += amount;

        IERC20(pools[poolId].token).transferFrom(msg.sender, address(this), amount);

        emit Stake(msg.sender, poolId, amount);
    }

    function withdraw(uint256 poolId, uint256 amount) external {
        require(poolId < pools.length, "Invalid pool");
        require(amount > 0, "Amount must be > 0");
        require(userStakes[poolId][msg.sender].amount >= amount, "Insufficient stake");

        _updateReward(poolId);

        uint256 reward = _getUserReward(poolId, msg.sender);
        userStakes[poolId][msg.sender].amount -= amount;
        userStakes[poolId][msg.sender].rewardDebt = _getUserRewardDebt(poolId, msg.sender);
        pools[poolId].totalStaked -= amount;
        totalUserStakes[msg.sender] -= amount;

        IERC20(pools[poolId].token).transfer(msg.sender, amount);

        if (reward > 0) {
            rewardToken.transfer(msg.sender, reward);
            emit RewardClaimed(msg.sender, poolId, reward);
        }

        emit Withdraw(msg.sender, poolId, amount);
    }

    function claimReward(uint256 poolId) external {
        require(poolId < pools.length, "Invalid pool");

        _updateReward(poolId);

        uint256 reward = _getUserReward(poolId, msg.sender);
        require(reward > 0, "No rewards to claim");

        userStakes[poolId][msg.sender].rewardDebt = _getUserRewardDebt(poolId, msg.sender);

        rewardToken.transfer(msg.sender, reward);
        emit RewardClaimed(msg.sender, poolId, reward);
    }

    function emergencyWithdraw(uint256 poolId) external {
        require(poolId < pools.length, "Invalid pool");
        
        uint256 amount = userStakes[poolId][msg.sender].amount;
        require(amount > 0, "No stake to withdraw");

        // Reset user's reward debt to zero
        userStakes[poolId][msg.sender].rewardDebt = 0;
        
        // Decrement pool's total staked
        pools[poolId].totalStaked -= amount;
        
        // Reset user's stake amount
        userStakes[poolId][msg.sender].amount = 0;
        
        // Update total user stakes
        totalUserStakes[msg.sender] -= amount;

        // Transfer staked tokens back to user
        IERC20(pools[poolId].token).transfer(msg.sender, amount);

        // Emit EmergencyWithdraw event
        emit EmergencyWithdraw(msg.sender, poolId, amount);
    }

    function _updateReward(uint256 poolId) internal {
        Pool storage pool = pools[poolId];
        if (block.timestamp > pool.lastUpdateTime && pool.totalStaked > 0) {
            uint256 elapsed = block.timestamp - pool.lastUpdateTime;
            uint256 rewards = elapsed * pool.rewardRate;
            pool.rewardPerTokenStored += (rewards * 1e18) / pool.totalStaked;
            pool.lastUpdateTime = block.timestamp;
        }
    }

    function _getUserReward(uint256 poolId, address user) internal view returns (uint256) {
        Pool storage pool = pools[poolId];
        UserStake storage stake = userStakes[poolId][user];
        return (stake.amount * (pool.rewardPerTokenStored - stake.rewardDebt)) / 1e18;
    }

    function _getUserRewardDebt(uint256 poolId, address user) internal view returns (uint256) {
        Pool storage pool = pools[poolId];
        UserStake storage stake = userStakes[poolId][user];
        return (stake.amount * pool.rewardPerTokenStored) / 1e18;
    }

    function getPoolInfo(uint256 poolId) external view returns (
        IERC20 token,
        uint256 totalStaked,
        uint256 rewardRate,
        uint256 lastUpdateTime,
        uint256 rewardPerTokenStored,
        bool active
    ) {
        Pool storage pool = pools[poolId];
        return (pool.token, pool.totalStaked, pool.rewardRate, pool.lastUpdateTime, pool.rewardPerTokenStored, pool.active);
    }

    function getUserStake(uint256 poolId, address user) external view returns (uint256 amount, uint256 rewardDebt) {
        UserStake storage stake = userStakes[poolId][user];
        return (stake.amount, stake.rewardDebt);
    }

    function getPoolCount() external view returns (uint256) {
        return pools.length;
    }
}
