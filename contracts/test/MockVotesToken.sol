// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";

contract MockVotesToken is ERC20Votes {
    constructor() ERC20("Mock Votes", "VOTE") EIP712("Mock Votes", "1") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
