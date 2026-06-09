// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract TestDeploy {
    string public name;
    uint256 public value;

    constructor(string memory _name, uint256 _value) {
        name = _name;
        value = _value;
    }
}

contract TestNoArgs {
    uint256 public value = 42;
}
