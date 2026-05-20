// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../CompoundVault.sol";

interface IMintBurnToken {
    function mint(address to, uint256 amount) external;
    function burnFromAny(address from, uint256 amount) external;
}

contract MockCompoundStrategy {
    IMintBurnToken public immutable token;
    address public vault;
    int256 public nextDelta;

    constructor(address token_) {
        token = IMintBurnToken(token_);
    }

    function setVault(address vault_) external {
        vault = vault_;
    }

    function setNextDelta(int256 delta) external {
        nextDelta = delta;
    }

    function compound() external {
        int256 delta = nextDelta;
        nextDelta = 0;

        if (delta > 0) {
            token.mint(vault, uint256(delta));
        } else if (delta < 0) {
            token.burnFromAny(vault, uint256(-delta));
        }
    }
}
