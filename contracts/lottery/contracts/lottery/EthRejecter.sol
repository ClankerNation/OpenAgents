// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title EthRejecter
/// @notice TEST-ONLY helper contract used by test/RandomLottery.test.js to simulate an
///     ETH-rejecting lottery winner (a contract with no receive/fallback function).
/// @dev Not used by any production contract. Verifies that RandomLottery pull-payment
///     keeps funds claimable instead of reverting the draw when a winner rejects ETH.
///
/// @contributor HCTDIP (minis-hunter-hctdip)
/// @platform-config Platform: Minis agent on iOS (iSH Alpine Linux, aarch64). Session: bounty #16
///     rework. Rules loaded pre-session: real data only, no gray traffic; single subagent <=15 min;
///     read-back verification after every write; one outbound message at a time (>=1 min interval);
///     TV slide on task completion.
/// @env os=linux arch=aarch64 home_dir=/root working_dir=/var/minis/workspace/sqlite-mcp shell=sh
/// @timestamp 2026-09-21T00:50:00Z
contract EthRejecter {
    address public lastCaller;

    // No receive() and no fallback(): any plain ETH transfer to this contract reverts.
    function ping() external {
        lastCaller = msg.sender;
    }
}
