// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title ReentrancyAttacker
/// @notice Malicious contract that attempts to re-enter StakingRewards.withdraw during a token transfer callback.
contract ReentrancyAttacker {
    address public stakingRewards;
    bool public inAttack;
    bool public reentrantCallSucceeded;

    event AttackStarted();
    event ReentrantCallAttempted(bool success);

    constructor(address _stakingRewards) {
        stakingRewards = _stakingRewards;
    }

    /// @notice Called by CallbackToken during transfer - tries to re-enter withdraw.
    function onTokenTransfer(address /*from*/, uint256 /*amount*/) external {
        emit AttackStarted();

        if (inAttack) {
            // Try to re-enter withdraw
            (bool success, ) = stakingRewards.call(
                abi.encodeWithSignature("withdraw(uint256)", 1)
            );
            emit ReentrantCallAttempted(success);
            reentrantCallSucceeded = success;
        }
    }

    /// @notice Setup: stake tokens via the staking contract.
    function stake(uint256 amount) external {
        (bool success, ) = stakingRewards.call(
            abi.encodeWithSignature("stake(uint256)", amount)
        );
        require(success, "Stake failed");
    }

    /// @notice Trigger the attack: call withdraw, which transfers tokens, which calls back to onTokenTransfer.
    function attack(uint256 amount) external {
        require(!inAttack, "ALREADY");
        inAttack = true;

        (bool success, ) = stakingRewards.call(
            abi.encodeWithSignature("withdraw(uint256)", amount)
        );
        require(success, "Withdraw failed");

        inAttack = false;

        // If the reentrant call succeeded, the attack worked (nonReentrant failed)
        // If it failed, nonReentrant is working correctly
        require(!reentrantCallSucceeded, "Reentrant call succeeded - attack worked!");
    }
}
