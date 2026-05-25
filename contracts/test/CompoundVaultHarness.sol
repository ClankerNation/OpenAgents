// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../vault/CompoundVault.sol";

contract CompoundVaultHarness is CompoundVault {
    constructor(
        address baseToken_,
        address rewardToken_,
        address strategy_,
        address feeRecipient_,
        uint256 feeBps_
    ) CompoundVault(baseToken_, rewardToken_, strategy_, feeRecipient_, feeBps_) {}

    function setAccounting(uint256 shares, uint256 deposited) external onlyOwner {
        totalShares = shares;
        totalDeposited = deposited;
    }

    function setLastPricePerShare(uint256 pricePerShare_) external onlyOwner {
        lastPricePerShare = pricePerShare_;
    }
}
