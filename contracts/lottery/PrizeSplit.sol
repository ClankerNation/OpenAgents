// [CodexBaseUSDCHunter] 2023-10-05T14:45:00Z
// npm install -g hardhat
// npx hardhat init
// node version: v18.16.0
// os: Windows 10
// arch: x64
// home_dir: C:\Users\Agent
// working_dir: C:\Projects\OpenAgents
// shell: PowerShell
//

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

contract PrizeSplit is ReentrancyGuard {
    // Existing contract code...
}
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

contract PrizeSplit is ReentrancyGuard {
    // existing contract code...
}

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

contract PrizeSplit is ReentrancyGuard {
    // Existing contract code...
}

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

contract PrizeSplit is ReentrancyGuard {
    // Existing contract code...
}

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";


    function claimPrize(address[] calldata winners, uint256[] calldata amounts) external nonReentrant {
        require(winners.length > 0, "No winners");
        require(winners.length == amounts.length, "Mismatched winners and amounts");

        uint256 totalAmount = 0;
        for (uint256 i = 0; i < amounts.length; i++) {
            require(winners[i] != address(0), "Zero address winner");
            totalAmount += amounts[i];
        }

        require(totalAmount <= address(this).balance, "Insufficient balance");

        uint256 dust = address(this).balance - totalAmount;

        for (uint256 i = 0; i < winners.length; i++) {
            bool success = payable(winners[i]).send(amounts[i]);
            require(success, "Transfer failed");
        }

        if (dust > 0) {
            bool success = payable(winners[winners.length - 1]).send(dust);
            require(success, "Dust transfer failed");
        }
    }
    }
    // Existing contract code...
