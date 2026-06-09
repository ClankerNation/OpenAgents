// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract TestDeploy {
    uint256 public value;
    string public name;

    constructor(uint256 _value, string memory _name) {
        value = _value;
        name = _name;
    }
}
