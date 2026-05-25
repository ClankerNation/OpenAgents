// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MockGovernorTarget {
    uint256 public value;

    event ValueSet(uint256 value);

    function setValue(uint256 value_) external {
        value = value_;
        emit ValueSet(value_);
    }
}
