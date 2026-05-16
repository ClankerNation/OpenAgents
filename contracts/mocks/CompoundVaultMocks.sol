// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockVaultToken is ERC20 {
    constructor(string memory name_, string memory symbol_) ERC20(name_, symbol_) {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    function slash(address account, uint256 amount) external {
        _burn(account, amount);
    }
}

contract MockCompoundStrategy {
    MockVaultToken public immutable token;
    int256 public nextReturn;

    constructor(address token_) {
        token = MockVaultToken(token_);
    }

    function setNextReturn(int256 amount) external {
        nextReturn = amount;
    }

    function compound() external {
        int256 amount = nextReturn;
        nextReturn = 0;

        if (amount > 0) {
            token.mint(msg.sender, uint256(amount));
        } else if (amount < 0) {
            token.slash(msg.sender, uint256(-amount));
        }
    }
}
