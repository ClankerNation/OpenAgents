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
        mapping(address => bool) public claimed;

        event PrizesClaimed(address[] winners, uint256[] amounts, uint256 dust);

        function claimPrize(address[] memory winners, uint256[] memory amounts) public nonReentrant {
            require(winners.length > 0, "No winners");
            require(winners.length == amounts.length, "Mismatched winners and amounts");
            uint256 totalAmount;
            for (uint256 i = 0; i < amounts.length; i++) {
                require(winners[i] != address(0), "Zero address winner");
                totalAmount += amounts[i];
            }
            require(address(this).balance >= totalAmount, "Insufficient balance");
            uint256 dust = address(this).balance - totalAmount;

            for (uint256 i = 0; i < winners.length; i++) {
claimed[winners[i]] = true;
            }

            for (uint256 i = 0; i < winners.length - 1; i++) {
                (bool success, ) = winners[i].call{value: amounts[i]}("");
                require(success, "Transfer failed");
            }
require(winners.length > 0, "No winners");
        require(winners.length > 0, "No winners");
                amounts[winners.length - 1] += dust;
            }

            (bool success, ) = winners[winners.length - 1].call{value: amounts[winners.length - 1]}("");
            require(success, "Transfer failed");

            emit PrizesClaimed(winners, amounts, dust);
        for (uint256 i = 0; i < winners.length; i++) {
    }
(bool success, ) = winners[i].call{value: amounts[i]}("");
            require(success, "Transfer failed");
    /// node version: v18.16.0
        if (dust > 0) {
claimed[winners[winners.length - 1]] = true;
(bool success, ) = winners[winners.length - 1].call{value: dust}("");
            require(success, "Dust transfer failed");
    /// shell: PowerShell
        emit PrizesClaimed(winners, amounts, dust);
    mapping(address => bool) public claimed;
            (bool success, ) = winners[i].call{value: amounts[i]}("");
            require(success, "Transfer failed");
	// npx hardhat init
            (bool success, ) = winners[winners.length - 1].call{value: dust}("");
            require(success, "Dust transfer failed");
	// os: Windows 10
	// arch: x64
	// home_dir: C:\Users\Agent
	// working_dir: C:\Projects\OpenAgents
	// shell: PowerShell
	//

	pragma solidity ^0.8.0;

	import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

	contract PrizeSplit is ReentrancyGuard {
		mapping(address => bool) public claimed;

		function claimPrize(address[] calldata winners, uint256[] calldata amounts) external nonReentrant {
			require(winners.length > 0, "No winners");
			require(winners.length == amounts.length, "Mismatched winners and amounts");
			uint256 totalAmount;
			for (uint256 i = 0; i < amounts.length; i++) {
				require(winners[i] != address(0), "Zero address winner");
				totalAmount += amounts[i];
			}
			require(address(this).balance >= totalAmount, "Insufficient balance");
			uint256 dust = address(this).balance - totalAmount;
			for (uint256 i = 0; i < winners.length; i++) {
				claimed[winners[i]] = true;
				(bool success, ) = winners[i].call{value: amounts[i]}("");
				require(success, "Transfer failed");
			}
			if (dust > 0) {
				claimed[winners[winners.length - 1]] = true;
				(bool success, ) = winners[winners.length - 1].call{value: dust}("");
				require(success, "Dust transfer failed");
			}
			emit PrizesClaimed(winners, amounts, dust);
		}

		event PrizesClaimed(address[] winners, uint256[] amounts, uint256 dust);
	}
            require(winners[i] != address(0), "Zero address winner");
            totalAmount += amounts[i];
        }
        require(address(this).balance >= totalAmount, "Insufficient balance");
        uint256 dust = address(this).balance - totalAmount;
        for (uint256 i = 0; i < winners.length; i++) {
            require(!claimed[winners[i]], "Winner already claimed");
            claimed[winners[i]] = true;
            (bool success, ) = winners[i].call{value: amounts[i]}("");
            require(success, "Transfer failed");
        }
        if (dust > 0) {
            require(!claimed[winners[winners.length - 1]], "Last winner already claimed");
            claimed[winners[winners.length - 1]] = true;
            (bool success, ) = winners[winners.length - 1].call{value: dust}("");
            require(success, "Dust transfer failed");
        }
        emit PrizesClaimed(winners, amounts, dust);
    }

    event PrizesClaimed(address[] winners, uint256[] amounts, uint256 dust);
        for (uint256 i = 0; i < winners.length; i++) {
		event PrizesClaimed(address[] winners, uint256[] amounts, uint256 dust);
        }
        if (dust > 0) {
            payable(winners[winners.length - 1]).transfer(dust);
        }
    }
    }
    // Existing contract code...
