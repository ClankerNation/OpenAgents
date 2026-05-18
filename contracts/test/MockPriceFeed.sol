// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Minimal price feed mock that always returns a fixed price for testing.
contract MockPriceFeed {
    uint256 public price = 1e18; // $1.00 in 18-decimal precision

    function getPrice(address /* token */) external view returns (uint256) {
        return price;
    }

    function setPrice(uint256 _price) external {
        price = _price;
    }
}
