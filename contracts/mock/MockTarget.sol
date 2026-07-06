// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title MockTarget — dummy contract for testing Timelock execution
contract MockTarget {
    uint256 public lastValue;
    string public lastString;

    event SomethingDone(uint256 value, address caller);

    function doSomething(uint256 _value) external {
        lastValue = _value;
        emit SomethingDone(_value, msg.sender);
    }

    function doString(string calldata _str) external {
        lastString = _str;
    }

    receive() external payable {}
}
