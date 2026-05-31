// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MockPriceFeed {
    uint256 public price = 1e18;

    function setPrice(uint256 newPrice) external {
        price = newPrice;
    }

    function getPrice(address) external view returns (uint256) {
        return price;
    }
}
