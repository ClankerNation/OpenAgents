// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../dex/AMMPool.sol";

contract AMMPoolHarness is AMMPool {
    constructor(address tokenA, address tokenB) AMMPool(tokenA, tokenB) {}
}
