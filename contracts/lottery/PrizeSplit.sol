/**
 * Agent: CodexBaseUSDCHunter
 * Timestamp: 2023-10-06T10:00:00Z
 * Runtime: {
 *   arch: "x64",
 *   home_dir: "C:\Users\Agent",
 *   working_dir: "C:\Projects\OpenAgents",
 *   shell: "PowerShell"
 * }
 */
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

contract PrizeSplit is ReentrancyGuard {
    mapping(address => uint256) public pendingPrizes;
    mapping(address => bool) public claimed;
    event PrizeClaimed(address indexed claimer, uint256 amount);
    event PrizesClaimed(address[] winners, uint256[] amounts, uint256 dust);

    function claimPrize(address[] calldata winners, uint256[] calldata amounts) external nonReentrant {
        require(winners.length > 0, "No winners");
        require(winners.length == amounts.length, "Mismatched winners and amounts");
        uint256 totalAmount = 0;
        uint256 dust = 0;

        for (uint256 i = 0; i < winners.length; i++) {
            require(winners[i] != address(0), "Zero address winner");
            totalAmount += amounts[i];
            claimed[winners[i]] = true;
        }

        require(address(this).balance >= totalAmount, "Insufficient balance");
        dust = address(this).balance - totalAmount;
        amounts[winners.length - 1] += dust;

        for (uint256 i = 0; i < winners.length; i++) {
            (bool success, ) = payable(winners[i]).call{value: amounts[i]}("");
            require(success, "Transfer failed");
            emit PrizeClaimed(winners[i], amounts[i]);
        }

        emit PrizesClaimed(winners, amounts, dust);
    }
}
