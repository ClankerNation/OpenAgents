// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "../governance/GovernorAlpha.sol";

/// @title TestGovernorAlpha
/// @notice GovernorAlpha with short voting period for fast testing.
contract TestGovernorAlpha is GovernorAlpha {
    constructor(address _token) GovernorAlpha(_token) {}

    function VOTING_DELAY() public pure override returns (uint256) { return 0; }
    function VOTING_PERIOD() public pure override returns (uint256) { return 5; }
    function DEFAULT_QUORUM_VOTES() public pure override returns (uint256) { return 1_000_000e18; }
}
