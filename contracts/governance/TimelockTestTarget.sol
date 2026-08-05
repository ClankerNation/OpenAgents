// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract TimelockTestTarget {
    uint256 public value;

    function setValue(uint256 newValue) external {
        value = newValue;
    }
}
