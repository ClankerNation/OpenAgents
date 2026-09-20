// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title EthRejecter
/// @notice TEST-ONLY helper: simulates an ETH-rejecting lottery winner (a contract with
///     no receive/fallback function, so plain ETH transfers to it revert).
/// @dev Used by test/RandomLottery.test.js to verify that RandomLottery pull-payment
///     keeps the draw completing and funds accounted in pendingPrizes, instead of the
///     draw reverting and locking the entire pool.
///
/// @contributor HCTDIP (minis-hunter-hctdip)
/// @platform-config Platform: Minis agent on iOS (iSH Alpine Linux, aarch64). Session: bounty #16
///     rework. Rules loaded pre-session: real data only, no gray traffic; single subagent <=15 min;
///     read-back verification after every write; one outbound message at a time (>=1 min interval);
///     TV slide on task completion.
/// @env os=linux arch=aarch64 home_dir=/root working_dir=/var/minis/workspace/sqlite-mcp shell=sh
/// @timestamp 2026-09-21T01:05:00Z

interface ILottery {
    function buyTicket() external payable;
    function claimPrize(uint256 round) external;
}

contract EthRejecter {
    // No receive() and no fallback(): any plain ETH transfer to this contract reverts.
    function join(address lottery) external payable {
        ILottery(lottery).buyTicket{value: msg.value}();
    }

    function tryClaim(address lottery, uint256 round) external {
        ILottery(lottery).claimPrize(round);
    }
}
