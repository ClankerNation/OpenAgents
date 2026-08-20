// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor rafaio1
 * @timestamp 2026-08-20T01:00:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */


/**
 * @fix-author rafaio1
 * @date 2026-08-20T00:00:00Z
 * @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-instructions [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */

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
        require(payee != address(0), "Invalid payee");
        require(amount > 0, "Amount must be > 0");

        // Balance-before/after check to handle fee-on-transfer tokens correctly
        uint256 balanceBefore = IERC20(token).balanceOf(address(this));
        IERC20(token).transferFrom(msg.sender, address(this), amount);
        uint256 actualReceived = IERC20(token).balanceOf(address(this)) - balanceBefore;
        
        require(actualReceived > 0, "Actual received amount must be > 0");

        uint256 escrowId = escrowCount++;
        escrows[escrowId] = Escrow({
            payer: msg.sender,
            payee: payee,
            token: token,
            amount: actualReceived, // Store actual received amount, not input amount
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

    // Timelock ownership transfer
    address private _pendingOwner;
    uint256 private _ownershipTransferDeadline;
    uint256 public constant OWNERSHIP_TIMELOCK = 2 days;

    event OwnershipTransferStarted(address indexed previousOwner, address indexed newOwner, uint256 deadline);
    event OwnershipTransferAccepted(address indexed previousOwner, address indexed newOwner);
    event OwnershipTransferCancelled(address indexed previousOwner, address indexed cancelledOwner);

    /// @notice Start ownership transfer with 2-day timelock.
    /// @param newOwner Address of the pending owner.
    function transferOwnership(address newOwner) public override onlyOwner {
        require(newOwner != address(0), "Ownable: zero address");
        require(newOwner != owner(), "Ownable: same owner");
        _pendingOwner = newOwner;
        _ownershipTransferDeadline = block.timestamp + OWNERSHIP_TIMELOCK;
        emit OwnershipTransferStarted(owner(), newOwner, _ownershipTransferDeadline);
    }

    /// @notice Accept ownership after timelock period.
    function acceptOwnership() external {
        require(msg.sender == _pendingOwner, "Ownable: not pending owner");
        require(block.timestamp >= _ownershipTransferDeadline, "Ownable: timelock active");
        
        address oldOwner = owner();
        _transferOwnership(_pendingOwner);
        _pendingOwner = address(0);
        _ownershipTransferDeadline = 0;
        emit OwnershipTransferAccepted(oldOwner, msg.sender);
    }

    /// @notice Cancel pending ownership transfer.
    function cancelOwnershipTransfer() external onlyOwner {
        require(_pendingOwner != address(0), "Ownable: no pending transfer");
        address cancelled = _pendingOwner;
        _pendingOwner = address(0);
        _ownershipTransferDeadline = 0;
        emit OwnershipTransferCancelled(owner(), cancelled);
    }

    /// @notice Get pending owner address.
    function pendingOwner() external view returns (address) {
        return _pendingOwner;
    }

    /// @notice Get ownership transfer deadline.
    function ownershipTransferDeadline() external view returns (uint256) {
        return _ownershipTransferDeadline;
    }

}
