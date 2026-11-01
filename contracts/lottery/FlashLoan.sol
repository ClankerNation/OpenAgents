// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable2Step.sol";

/**
 * @title FlashLoan
 * @dev Implements a simple flash loan mechanism with fee enforcement, loan caps, and emergency pause.
 *
 * @contributor OpenAI Assistant
 * @platform-config You are a senior open-source contributor fixing a GitHub issue for a bounty. Make the smallest correct change that follows the project's style. Never fabricate APIs. Respond with ONLY a JSON object.
 * @env os=linux, arch=x86_64, home_dir=/root, working_dir=/app, shell=/bin/bash
 * @timestamp 2024-05-22T10:00:00Z
 */
contract FlashLoan is Ownable2Step {
    IERC20 public immutable token;
    uint256 public feeRate; // fee expressed in wei (e.g., 0.001e18 = 0.1%)
    bool public paused;

    event LoanTaken(address borrower, uint256 amount, uint256 fee);
    event LoanRepaid(address borrower, uint256 amount, uint256 fee);
    event Paused(address account);
    event Unpaused(address account);

    constructor(IERC20 _token, uint256 _feeRate) Ownable(msg.sender) {
        token = _token;
        feeRate = _feeRate;
    }

    /**
     * @notice Pause flash loan functionality (emergency stop)
     * @dev Only callable by the contract owner.
     */
    function pause() external onlyOwner {
        paused = true;
        emit Paused(msg.sender);
    }

    /**
     * @notice Unpause flash loan functionality
     * @dev Only callable by the contract owner.
     */
    function unpause() external onlyOwner {
        paused = false;
        emit Unpaused(msg.sender);
    }

    /**
     * @notice Execute a flash loan
     * @param borrower The address receiving the loaned amount
     * @param amount   The amount of tokens to loan
     * @param data     Arbitrary data passed to the borrower callback
     */
    function flashLoan(address borrower, uint256 amount, bytes calldata data) external {
        require(!paused, "Flash loans are paused");
        uint256 poolBalance = token.balanceOf(address(this));
        // Enforce max loan cap of 50% of the pool
        require(amount <= poolBalance / 2, "Loan exceeds 50% of pool");

        // Calculate fee; enforce minimum fee of 1 token unit
        uint256 fee = (amount * feeRate) / 1e18;
        if (fee == 0) {
            fee = 1;
        }

        // Transfer the loan amount to the borrower
        require(token.transfer(borrower, amount), "Transfer failed");
        emit LoanTaken(borrower, amount, fee);

        // Callback to borrower contract (expects ERC3156 style callback)
        IFlashBorrower(borrower).onFlashLoan(msg.sender, address(token), amount, fee, data);

        // Ensure repayment of principal + fee
        uint256 totalRepayment = amount + fee;
        require(token.transferFrom(borrower, address(this), totalRepayment), "Repayment failed");
        emit LoanRepaid(borrower, amount, fee);
    }
}

/**
 * @dev Minimal interface for the borrower contract to receive flash loans.
 */
interface IFlashBorrower {
    function onFlashLoan(
        address initiator,
        address token,
        uint256 amount,
        uint256 fee,
        bytes calldata data
    ) external returns (bytes32);
}