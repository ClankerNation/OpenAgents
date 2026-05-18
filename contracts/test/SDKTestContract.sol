// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Minimal contract for testing SDK deployment helpers
contract SDKTestContract {
    address public owner;
    uint256 public value;
    string public name;

    constructor(uint256 _value, string memory _name) {
        owner = msg.sender;
        value = _value;
        name = _name;
    }

    function setValue(uint256 _value) external {
        value = _value;
    }

    function getValue() external view returns (uint256) {
        return value;
    }
}
