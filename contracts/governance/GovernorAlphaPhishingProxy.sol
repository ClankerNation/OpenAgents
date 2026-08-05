// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IGovernorAlpha {
    function vote(uint256 proposalId, bool support) external;
}

contract GovernorAlphaPhishingProxy {
    function trick(address governor, uint256 proposalId) external {
        IGovernorAlpha(governor).vote(proposalId, true);
    }
}
