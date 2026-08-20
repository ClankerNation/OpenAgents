// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor rafaio1
 * @timestamp 2026-08-20T00:00:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */

interface IPriceFeed {
    function getPrice(address token) external view returns (uint256);
}

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @title LendingPool
/// @notice Collateralized lending pool with flash loan liquidation support
/// @dev Uses an external price feed oracle for collateral valuation
contract LendingPool {
    IPriceFeed public oracle;
    IERC20 public collateralToken;
    IERC20 public borrowToken;

    uint256 public constant LIQUIDATION_THRESHOLD = 1.5e18; // 150%
    uint256 public constant PRECISION = 1e18;
    uint256 public constant FLASH_LOAN_FEE_BPS = 9; // 0.09% like Aave

    struct Position {
        uint256 collateralAmount;
        uint256 borrowedAmount;
    }

    mapping(address => Position) public positions;
    uint256 public totalDeposits;
    uint256 public totalBorrowed;

    event Deposited(address indexed user, uint256 amount);
    event Borrowed(address indexed user, uint256 amount);
    event Repaid(address indexed user, uint256 amount);
    event Liquidated(address indexed user, address indexed liquidator, uint256 debtRepaid);
    event FlashLiquidated(address indexed user, address indexed liquidator, uint256 debtRepaid, uint256 profit);

    constructor(address _oracle, address _collateralToken, address _borrowToken) {
        oracle = IPriceFeed(_oracle);
        collateralToken = IERC20(_collateralToken);
        borrowToken = IERC20(_borrowToken);
    }

    function deposit(uint256 amount) external {
        require(amount > 0, "Zero amount");
        require(collateralToken.transferFrom(msg.sender, address(this), amount), "Transfer failed");
        positions[msg.sender].collateralAmount += amount;
        totalDeposits += amount;
        emit Deposited(msg.sender, amount);
    }

    function borrow(uint256 amount) external {
        require(amount > 0, "Zero amount");
        positions[msg.sender].borrowedAmount += amount;
        totalBorrowed += amount;

        require(_isHealthy(msg.sender), "Undercollateralized");
        require(borrowToken.transfer(msg.sender, amount), "Transfer failed");
        emit Borrowed(msg.sender, amount);
    }

    function repay(uint256 amount) external {
        Position storage pos = positions[msg.sender];
        require(amount <= pos.borrowedAmount, "Repay exceeds debt");
        require(borrowToken.transferFrom(msg.sender, address(this), amount), "Transfer failed");
        pos.borrowedAmount -= amount;
        totalBorrowed -= amount;
        emit Repaid(msg.sender, amount);
    }

    function liquidate(address user) external {
        require(!_isHealthy(user), "Position healthy");

        Position storage pos = positions[user];
        uint256 debt = pos.borrowedAmount;
        uint256 collateral = pos.collateralAmount;

        require(borrowToken.transferFrom(msg.sender, address(this), debt), "Transfer failed");

        pos.borrowedAmount = 0;
        pos.collateralAmount = 0;
        totalBorrowed -= debt;
        totalDeposits -= collateral;

        require(collateralToken.transfer(msg.sender, collateral), "Transfer failed");
        emit Liquidated(user, msg.sender, debt);
    }

    /// @notice Flash loan liquidation: borrow funds, liquidate position, repay + fee in one tx.
    /// @param user The underwater position to liquidate.
    /// @dev Liquidator receives collateral minus flash loan repayment and fee as profit.
    function flashLiquidate(address user) external nonReentrant {
        require(!_isHealthy(user), "Position healthy");

        Position storage pos = positions[user];
        uint256 debt = pos.borrowedAmount;
        uint256 collateral = pos.collateralAmount;

        require(debt > 0, "No debt to liquidate");

        // Calculate flash loan fee
        uint256 fee = (debt * FLASH_LOAN_FEE_BPS) / 10000;
        uint256 totalRepayment = debt + fee;

        // Verify pool has enough borrow tokens to lend
        require(borrowToken.balanceOf(address(this)) >= debt, "Insufficient pool liquidity");

        // Transfer borrow tokens to liquidator (flash loan)
        require(borrowToken.transfer(msg.sender, debt), "Flash loan transfer failed");

        // Liquidator must return totalRepayment within this transaction
        // In practice, liquidator would use a callback or inline logic.
        // Here we assume the liquidator has already approved repayment or uses
        // a contract that repays within the same tx via delegatecall pattern.
        // For simplicity, we pull the repayment immediately.
        require(
            borrowToken.transferFrom(msg.sender, address(this), totalRepayment),
            "Flash loan repayment failed"
        );

        // Clear the position
        pos.borrowedAmount = 0;
        pos.collateralAmount = 0;
        totalBorrowed -= debt;
        totalDeposits -= collateral;

        // Transfer collateral to liquidator (their profit is collateral value minus repayment cost)
        require(collateralToken.transfer(msg.sender, collateral), "Collateral transfer failed");

        emit FlashLiquidated(user, msg.sender, debt, collateral);
    }

    function _isHealthy(address user) internal view returns (bool) {
        Position storage pos = positions[user];
        if (pos.borrowedAmount == 0) return true;

        uint256 collateralPrice = oracle.getPrice(address(collateralToken));
        uint256 borrowPrice = oracle.getPrice(address(borrowToken));

        require(collateralPrice > 0 && borrowPrice > 0, "Invalid oracle price");

        uint256 collateralValue = (pos.collateralAmount * collateralPrice) / PRECISION;
        uint256 borrowValue = (pos.borrowedAmount * borrowPrice) / PRECISION;

        return collateralValue >= (borrowValue * LIQUIDATION_THRESHOLD) / PRECISION;
    }

    function getPosition(address user) external view returns (uint256 collateral, uint256 debt) {
        Position storage pos = positions[user];
        return (pos.collateralAmount, pos.borrowedAmount);
    }
}
