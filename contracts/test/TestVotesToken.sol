// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";

contract TestVotesToken is ERC20Votes {
    constructor() ERC20("TestVotes", "VOTE") EIP712("TestVotes", "1") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
