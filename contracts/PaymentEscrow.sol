// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

// Contributor: Claude (Anthropic AI Assistant)
// Platform: Claude 3.5 Sonnet on Anthropic
// Runtime: Solidity 0.8.19
// OS: darwin | Arch: arm64 | WD: /contracts | Shell: /bin/zsh
// Init: You are opencode, CLI tool for software engineering. Env: macOS darwin arm64 zsh Python 3.11.

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract PaymentEscrow is Ownable {
    struct Escrow {
        address token;
        address payee;
        uint256 amount;
        bool released;
    }
    mapping(uint256 => Escrow) public escrows;
    uint256 public escrowCount;
    event EscrowCreated(uint256 id, address token, address payee, uint256 amount);
    event EscrowReleased(uint256 id);
    
    function createEscrow(address token_, address payee_, uint256 amount_) external returns (uint256) {
        require(amount_ > 0, "PaymentEscrow: zero amount");
        require(payee_ != address(0), "PaymentEscrow: invalid payee");
        uint256 balanceBefore = IERC20(token_).balanceOf(address(this));
        require(IERC20(token_).transferFrom(msg.sender, address(this), amount_), "PaymentEscrow: transfer failed");
        uint256 balanceAfter = IERC20(token_).balanceOf(address(this));
        uint256 actualReceived = balanceAfter - balanceBefore;
        require(actualReceived > 0, "PaymentEscrow: zero received after transfer");
        escrows[escrowCount] = Escrow(token_, payee_, actualReceived, false);
        emit EscrowCreated(escrowCount, token_, payee_, actualReceived);
        escrowCount++;
        return escrowCount - 1;
    }
    
    function release(uint256 id) external {
        Escrow storage escrow = escrows[id];
        require(!escrow.released, "PaymentEscrow: already released");
        require(msg.sender == escrow.payee || msg.sender == owner(), "PaymentEscrow: not authorized");
        escrow.released = true;
        require(IERC20(escrow.token).transfer(escrow.payee, escrow.amount), "PaymentEscrow: release failed");
        emit EscrowReleased(id);
    }
}
