// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title FlashLoan
/// @notice Minimal flash loan contract with fee floor, max cap, and pause protection.
/// @custom:contributor Hermes Agent Bot
/// @custom:date 2026-07-05T08:05:00Z
/// @custom:platform Hermes Agent by Nous Research -- autonomous AI agent running in WSL (Ubuntu linux x86_64)
/// @custom:runtime os=linux, arch=x86_64, home_dir=/home/nana, working_dir=/tmp, shell=/usr/bin/bash
/// @custom:instructions Hermes Agent Bot autonomous income agent -- operated under CEO/entrepreneur persona.
///     Autonomous AI agent that scans freelance/AI-task platforms, finds high-profit work, and executes with minimal token cost.
///     Operating with 7-day runway, 100 yuan token budget. Core identity: Brain/CEO, not executor.
///     Decision framework: First Principles + Human Nature + Business Model.
///     Autonomy mandate: zero dependence on human operator. Never ask for login, screenshots, or decisions.
///     Bounty hunter rules: quality over speed, no continuous polling, use cron with 15-30min intervals.
contract FlashLoan {
    address public owner;
    bool public paused;
    uint256 public constant MAX_LOAN_PERCENT = 50; // percent of pool
    uint256 public constant MIN_FEE = 1; // minimum fee of 1 token

    mapping(address => uint256) public poolBalances;

    event LoanInitiated(address indexed user, uint256 amount, uint256 fee);
    event LoanRepaid(address indexed user, uint256 amount, uint256 fee);
    event Paused();
    event Unpaused();

    modifier onlyOwner() {
        require(msg.sender == owner, "FlashLoan: not owner");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "FlashLoan: paused");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /// @notice Initiate a flash loan. Max loan is 50% of pool. Minimum fee of 1 token.
    function initiateLoan(uint256 amount) external whenNotPaused returns (uint256 fee) {
        require(amount > 0, "FlashLoan: zero amount");
        uint256 poolSize = address(this).balance;
        require(poolSize > 0, "FlashLoan: empty pool");
        require(amount <= (poolSize * MAX_LOAN_PERCENT) / 100, "FlashLoan: exceeds max loan percent");

        // Calculate fee: minimum of 1 token, or percentage-based
        fee = amount / 100; // 1% fee
        if (fee < MIN_FEE) {
            fee = MIN_FEE;
        }

        require(address(this).balance >= amount + fee, "FlashLoan: insufficient balance");

        poolBalances[msg.sender] = amount;

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "FlashLoan: transfer failed");

        emit LoanInitiated(msg.sender, amount, fee);
    }

    /// @notice Repay a flash loan with fee.
    function repayLoan() external payable {
        uint256 borrowed = poolBalances[msg.sender];
        require(borrowed > 0, "FlashLoan: no active loan");

        uint256 fee = borrowed / 100;
        if (fee < MIN_FEE) {
            fee = MIN_FEE;
        }

        uint256 totalDue = borrowed + fee;
        require(msg.value >= totalDue, "FlashLoan: insufficient repayment");

        poolBalances[msg.sender] = 0;

        // Refund excess
        if (msg.value > totalDue) {
            (bool refundSent, ) = msg.sender.call{value: msg.value - totalDue}("");
            require(refundSent, "FlashLoan: refund failed");
        }

        emit LoanRepaid(msg.sender, borrowed, fee);
    }

    function pause() external onlyOwner {
        paused = true;
        emit Paused();
    }

    function unpause() external onlyOwner {
        paused = false;
        emit Unpaused();
    }

    receive() external payable {
        // Accept deposits to pool
    }
}
