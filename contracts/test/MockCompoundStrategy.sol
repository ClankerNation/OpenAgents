// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IMockVaultToken {
    function mint(address to, uint256 amount) external;
    function burnFromAny(address from, uint256 amount) external;
}

contract MockCompoundStrategy {
    enum Mode {
        Zero,
        Gain,
        Loss
    }

    IMockVaultToken public immutable token;
    address public vault;
    Mode public mode;
    uint256 public amount;

    constructor(address token_) {
        token = IMockVaultToken(token_);
    }

    function setVault(address vault_) external {
        vault = vault_;
    }

    function setReturn(Mode mode_, uint256 amount_) external {
        mode = mode_;
        amount = amount_;
    }

    function compound() external {
        require(vault != address(0), "Strategy: vault not set");
        if (mode == Mode.Gain) {
            token.mint(vault, amount);
        } else if (mode == Mode.Loss) {
            token.burnFromAny(vault, amount);
        }
    }
}
