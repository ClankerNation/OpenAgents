// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockFeeOnTransferToken is ERC20 {
    uint256 public immutable feeBps;

    constructor(string memory name_, string memory symbol_, uint256 feeBps_) ERC20(name_, symbol_) {
        require(feeBps_ <= 1_000, "Fee too high");
        feeBps = feeBps_;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    function _update(address from, address to, uint256 value) internal override {
        if (from != address(0) && to != address(0) && feeBps > 0) {
            uint256 fee = (value * feeBps) / 10_000;
            uint256 net = value - fee;

            if (fee > 0) {
                super._update(from, address(0), fee);
            }
            super._update(from, to, net);
            return;
        }

        super._update(from, to, value);
    }
}
