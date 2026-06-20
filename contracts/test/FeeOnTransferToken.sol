// SPDX-License-Identifier: MIT
// @contributor: Claude Code (Claude Opus 4.7)
// @platform-config: Task: Create fee-on-transfer token for PaymentEscrow testing. Rules: 5% fee on transfer, burn fee tokens. Tools: npx hardhat. Style: Solidity conventions per project.
// @env: os=linux, arch=x86_64, home_dir=/home/michael, working_dir=/home/michael/web3-community/OpenAgents, shell=bash
// @timestamp: 2026-06-20T08:00:00Z
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @notice ERC20 that deducts a 5% fee on every transfer.
/// The fee is burned, so the recipient always receives 95% of the sent amount.
contract FeeOnTransferToken is ERC20 {
    uint256 public constant FEE_BPS = 500; // 5%

    constructor(string memory name, string memory symbol) ERC20(name, symbol) {
        _mint(msg.sender, 1_000_000 * 10 ** decimals());
    }

    function _update(address from, address to, uint256 value) internal override {
        if (from == address(0) || to == address(0)) {
            super._update(from, to, value);
            return;
        }
        uint256 fee = (value * FEE_BPS) / 10000;
        uint256 net = value - fee;
        super._update(from, to, net);
        if (fee > 0) {
            super._update(from, address(0), fee); // burn
        }
    }
}
