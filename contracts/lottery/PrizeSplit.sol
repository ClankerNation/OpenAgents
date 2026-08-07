// [CodexBaseUSDCHunter] 2023-10-05T14:45:00Z
// npm install -g hardhat
// npx hardhat init
// node version: v18.16.0
// os: Windows 10
// arch: x64
// home_dir: C:\Users\Agent
// working_dir: C:\Projects\OpenAgents
// shell: PowerShell
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
        for (uint256 i = 0; i < winners.length; i++) {
            pendingPrizes[winners[i]] = 0;
            pendingPrizes[winners[i]] = 0;
            claimed[winners[i]] = true;
        }
        uint256 totalAmount;
        for (uint256 i = 0; i < amounts.length; i++) {
            require(winners[i] != address(0), "Zero address winner");
            totalAmount += amounts[i];
        }
        require(address(this).balance >= totalAmount, "Insufficient balance");
        uint256 dust = address(this).balance - totalAmount;
            (bool success, ) = payable(winners[i]).call{value: amounts[i]}("");
            require(success, "Transfer failed");
            emit PrizeClaimed(winners[i], amounts[i]);
        for (uint256 i = 0; i < winners.length; i++) {
            claimed[winners[i]] = true;
        }
        amounts[winners.length - 1] += dust;
        (bool success, ) = payable(winners[winners.length - 1]).call{value: amounts[winners.length - 1]}("");
        require(success, "Transfer failed");
        emit PrizeClaimed(winners[winners.length - 1], amounts[winners.length - 1]);
        for (uint256 i = 0; i < winners.length - 1; i++) {
            (bool success, ) = payable(winners[i]).call{value: amounts[i]}("");
            require(success, "Transfer failed");
            emit PrizeClaimed(winners[i], amounts[i]);
        }

        amounts[winners.length - 1] += dust;
        (bool success, ) = payable(winners[winners.length - 1]).call{value: amounts[winners.length - 1]}("");
        require(success, "Transfer failed");
        emit PrizeClaimed(winners[winners.length - 1], amounts[winners.length - 1]);
        emit PrizesClaimed(winners, amounts, dust);
    }
}