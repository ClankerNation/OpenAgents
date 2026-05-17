// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @title FeeOnTransferToken — Mock ERC20 that takes a fee on every transfer
/// @notice Used for testing PaymentEscrow's fee-on-transfer token handling.
///         5% of every transfer is burned; the recipient receives only 95%.
contract FeeOnTransferToken is ERC20 {
    uint256 public constant FEE_BPS = 500; // 5% fee in basis points
    uint256 public constant MAX_BPS = 10_000;

    constructor() ERC20("Fee Token", "FEETOK") {
        _mint(msg.sender, 1_000_000 * 10 ** decimals());
    }

    function transfer(address to, uint256 amount) public override returns (bool) {
        uint256 fee = (amount * FEE_BPS) / MAX_BPS;
        uint256 netAmount = amount - fee;

        _transfer(_msgSender(), to, netAmount);
        if (fee > 0) {
            _burn(_msgSender(), fee);
        }
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) public override returns (bool) {
        uint256 fee = (amount * FEE_BPS) / MAX_BPS;
        uint256 netAmount = amount - fee;

        _spendAllowance(from, _msgSender(), amount);
        _transfer(from, to, netAmount);
        if (fee > 0) {
            _burn(from, fee);
        }
        return true;
    }
}
