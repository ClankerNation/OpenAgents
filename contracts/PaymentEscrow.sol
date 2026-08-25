// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
// @fix-author rafaio1
// @date 2026-08-25T03:40:00Z
// @runtime linux x64 /tmp/openagents_issue_202 bash
// @platform-config Autonomous bounty execution pipeline initialized with SOLID/Object Calisthenics enforcement, senior dev multi-agent orchestration, and Wise payout integration.

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract PaymentEscrow is Ownable {
    struct Escrow {
        address payer;
        address payee;
        address token;
        uint256 amount;
        uint256 releaseTime;
        bool released;
        bool refunded;
    }

    mapping(uint256 => Escrow) public escrows;
    uint256 public escrowCount;

    event EscrowCreated(uint256 indexed escrowId, address indexed payer, uint256 amount);
    event EscrowReleased(uint256 indexed escrowId, address indexed payee, uint256 amount);
    event EscrowRefunded(uint256 indexed escrowId, address indexed payer, uint256 amount);

    constructor() Ownable(msg.sender) {}

    function createEscrow(
        address payee,
        address token,
        uint256 amount,
        uint256 lockDuration
    ) external returns (uint256) {
        require(payee != address(0), "PaymentEscrow: invalid payee");
        require(amount > 0, "PaymentEscrow: amount must be > 0");

        // Balance-before/after check handles fee-on-transfer tokens correctly
        uint256 balanceBefore = IERC20(token).balanceOf(address(this));
        IERC20(token).transferFrom(msg.sender, address(this), amount);
        uint256 actualReceived = IERC20(token).balanceOf(address(this)) - balanceBefore;
        require(actualReceived > 0, "PaymentEscrow: zero received after fees");

        uint256 escrowId = escrowCount++;
        escrows[escrowId] = Escrow({
            payer: msg.sender,
            payee: payee,
            token: token,
            amount: actualReceived, // Store actual received amount, not input
            releaseTime: block.timestamp + lockDuration,
            released: false,
            refunded: false
        });

        emit EscrowCreated(escrowId, msg.sender, actualReceived);
        return escrowId;
    }

    function releaseEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(msg.sender == escrow.payer || msg.sender == owner(), "Not authorized");

        escrow.released = true;
        IERC20(escrow.token).transfer(escrow.payee, escrow.amount);

        emit EscrowReleased(escrowId, escrow.payee, escrow.amount);
    }

    function refundEscrow(uint256 escrowId) external {
        Escrow storage escrow = escrows[escrowId];
        require(!escrow.released && !escrow.refunded, "Already settled");
        require(block.timestamp > escrow.releaseTime, "Lock not expired");
        require(msg.sender == escrow.payer, "Not payer");

        escrow.refunded = true;
        IERC20(escrow.token).transfer(escrow.payer, escrow.amount);

        emit EscrowRefunded(escrowId, escrow.payer, escrow.amount);
    }
}
