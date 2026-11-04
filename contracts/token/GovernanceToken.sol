// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";

/// @notice Votes-enabled ERC20 used by governor tests and local deployments.
contract GovernanceToken is ERC20Votes {
    constructor() ERC20("Governance Token", "GOV") EIP712("Governance Token", "1") {
        _mint(msg.sender, 1_000_000_000 ether);
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
