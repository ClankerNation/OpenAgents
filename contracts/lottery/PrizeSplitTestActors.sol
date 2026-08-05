// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IPrizeSplitClaims {
    function claimPrize(uint256 roundId) external;
}

/// @dev Test actor that attempts to claim the same round again from receive().
contract ReentrantWinner {
    address public target;
    uint256 public roundId;
    bool public reentrySucceeded;

    function attack(address target_, uint256 roundId_) external {
        target = target_;
        roundId = roundId_;
        IPrizeSplitClaims(target_).claimPrize(roundId_);
    }

    receive() external payable {
        (bool success, ) = target.call(
            abi.encodeWithSelector(IPrizeSplitClaims.claimPrize.selector, roundId)
        );
        if (success) {
            reentrySucceeded = true;
        }
    }
}
