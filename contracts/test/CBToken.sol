// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @title CallbackToken
/// @notice Mock ERC20 token that calls back to the recipient during transfer.
/// @dev Used to test reentrancy protection in StakingRewards.
contract CallbackToken is ERC20 {
    constructor() ERC20("CallbackToken", "CBT") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    /// @notice Force-set allowance for testing purposes.
    function forceApprove(address owner, address spender, uint256 amount) external {
        _approve(owner, spender, amount);
    }

    /// @notice Override transfer to call back to the recipient if they are a contract.
    function transfer(address to, uint256 amount) public override returns (bool) {
        address from = _msgSender();
        super.transfer(to, amount);

        // If the recipient is a contract, call it to trigger a potential reentrancy
        if (to.code.length > 0) {
            (bool success, ) = to.call(abi.encodeWithSignature("onTokenTransfer(address,uint256)", from, amount));
            success;
        }

        return true;
    }

    /// @notice Override transferFrom to call back to the recipient if they are a contract.
    function transferFrom(
        address from,
        address to,
        uint256 amount
    ) public override returns (bool) {
        super.transferFrom(from, to, amount);

        // If the recipient is a contract, call it to trigger a potential reentrancy
        if (to.code.length > 0) {
            (bool success, ) = to.call(abi.encodeWithSignature("onTokenTransfer(address,uint256)", from, amount));
            success;
        }

        return true;
    }
}
