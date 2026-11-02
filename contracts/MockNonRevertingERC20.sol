// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title MockNonRevertingERC20
 * @notice Mock ERC20 token whose transfer() returns false instead of reverting.
 * Used to test that TaskRouter uses SafeERC20.safeTransfer which reverts on
 * non-reverting token failures.
 */
contract MockNonRevertingERC20 {
    mapping(address => uint256) public balanceOf;

    function transfer(address to, uint256 amount) public returns (bool) {
        // Intentionally return false without moving funds — simulates
        // non-reverting ERC20s like USDT on failure.
        return false;
    }

    function transferFrom(
        address from,
        address to,
        uint256 amount
    ) public returns (bool) {
        return false;
    }

    function approve(address spender, uint256 amount) public returns (bool) {
        return true;
    }

    function allowance(
        address owner,
        address spender
    ) public view returns (uint256) {
        return 0;
    }
}
