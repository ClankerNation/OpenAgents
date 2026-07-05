// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract StakingRewards {
    IERC20 public stakingToken;
    IERC20 public rewardsToken;
    mapping(address => uint256) public stakedBalance;
    mapping(address => uint256) public lastUpdateTime;
    uint256 public rewardRate = 100;
    
    event Staked(address indexed user, uint256 amount);
    event RewardPaid(address indexed user, uint256 reward);
    
    constructor(address _staking, address _rewards) {
        stakingToken = IERC20(_staking);
        rewardsToken = IERC20(_rewards);
    }
    
    function _updateReward(address account) internal {
        if (lastUpdateTime[account] == 0) {
            lastUpdateTime[account] = block.timestamp;  // Fix #106: use block.timestamp
        }
        uint256 elapsed = block.timestamp - lastUpdateTime[account];  // Fix #106
        if (elapsed > 0 && stakedBalance[account] > 0) {
            uint256 reward = stakedBalance[account] * rewardRate * elapsed / 1e18;
            rewardsToken.transfer(account, reward);
            emit RewardPaid(account, reward);
        }
        lastUpdateTime[account] = block.timestamp;
    }
    
    function stake(uint256 amount) external {
        _updateReward(msg.sender);
        stakingToken.transferFrom(msg.sender, address(this), amount);
        stakedBalance[msg.sender] += amount;
        emit Staked(msg.sender, amount);
    }
}
