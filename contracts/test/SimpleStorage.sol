// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title SimpleStorage
/// @notice Minimal contract for testing SDK deployment functionality
contract SimpleStorage {
    uint256 private value;

    /// @notice Initializes storage with a given value
    /// @param _value Initial value to store
    constructor(uint256 _value) {
        value = _value;
    }

    /// @notice Updates the stored value
    /// @param _value New value to store
    function setValue(uint256 _value) public {
        value = _value;
    }

    /// @notice Returns the stored value
    /// @return The current stored value
    function retrieve() public view returns (uint256) {
        return value;
    }
}
