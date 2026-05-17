// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Contributor: Gaotax2006
// Platform: warpSpeed bounty agent, opencode CLI
// Runtime: OS=win32 Arch=x64 Home=C:\Users\asus WorkDir=F:\ai-bounty-work\bounty-hunter\openagents Shell=powershell
// Date: 2026-05-17

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

contract FlashLoan {
    IERC20 public token;
    address public owner;
    uint256 public feeBps;
    uint256 public constant MIN_FEE = 1;
    uint256 public constant MAX_LOAN_PERCENT = 5000;
    bool public paused;

    event FlashLoanExecuted(address indexed borrower, uint256 amount, uint256 fee);
    event Paused(address indexed by);
    event Unpaused(address indexed by);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "Paused");
        _;
    }

    constructor(address _token, uint256 _feeBps) {
        token = IERC20(_token);
        owner = msg.sender;
        feeBps = _feeBps;
    }

    function flashLoan(uint256 amount, address borrower, bytes calldata data) external onlyOwner whenNotPaused {
        require(amount > 0, "Zero amount");
        uint256 poolBalance = token.balanceOf(address(this));
        require(amount <= (poolBalance * MAX_LOAN_PERCENT) / 10000, "Exceeds max loan");

        uint256 fee = (amount * feeBps) / 10000;
        if (fee < MIN_FEE) {
            fee = MIN_FEE;
        }

        uint256 beforeBalance = token.balanceOf(address(this));
        require(token.transfer(borrower, amount), "Transfer failed");

        (bool success, ) = borrower.call(data);
        require(success, "Callback failed");

        uint256 afterBalance = token.balanceOf(address(this));
        require(afterBalance >= beforeBalance + fee, "Loan not repaid");

        emit FlashLoanExecuted(borrower, amount, fee);
    }

    function pause() external onlyOwner {
        paused = true;
        emit Paused(msg.sender);
    }

    function unpause() external onlyOwner {
        paused = false;
        emit Unpaused(msg.sender);
    }
}
