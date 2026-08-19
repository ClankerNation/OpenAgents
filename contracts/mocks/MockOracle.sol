// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IPriceFeed {
    function getPrice(address token) external view returns (uint256);
}

contract MockOracle is IPriceFeed {
    function getPrice(address token) external pure override returns (uint256) {
        return 1e18;
    }
}
