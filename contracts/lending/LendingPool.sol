// @contributor rafaio1
// @date 2026-08-21T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IPriceFeed {
    function getPrice(address token) external view returns (uint256);
}

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @title LendingPool
/// @notice Collateralized lending pool supporting deposit, borrow, repay, and liquidation
/// @dev Uses an external price feed oracle for collateral valuation
contract LendingPool {
    IPriceFeed public oracle;
    IERC20 public collateralToken;
    IERC20 public borrowToken;

    uint256 public constant LIQUIDATION_THRESHOLD = 1.25e18; // 125% - positions below this are liquidatable
    uint256 public constant LIQUIDATION_INCENTIVE = 1.05e18; // 5% bonus for liquidators
    uint256 public constant PRECISION = 1e18;
    uint256 public badDebtReserve; // Tracks socialized bad debt

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

    /// @notice Liquidate an undercollateralized position.
    /// @param user The borrower whose position to liquidate.
    function liquidate(address user) external {
        require(!_isHealthy(user), "LendingPool: position healthy");

        Position storage pos = positions[user];
        uint256 debt = pos.borrowedAmount;
        uint256 collateral = pos.collateralAmount;

        require(debt > 0, "LendingPool: no debt");

        // Get validated prices
        uint256 collateralPrice = oracle.getPrice(address(collateralToken));
        uint256 borrowPrice = oracle.getPrice(address(borrowToken));
        require(collateralPrice > 0, "LendingPool: invalid collateral price");
        require(borrowPrice > 0, "LendingPool: invalid borrow price");

        // Calculate collateral value and max repayable debt (with incentive)
        uint256 collateralValue = (collateral * collateralPrice) / PRECISION;
        // Liquidator gets collateral worth debtRepaid * incentive / borrowPrice
        // Max debt that can be repaid given available collateral:
        uint256 maxDebtRepayable = (collateralValue * PRECISION) / (LIQUIDATION_INCENTIVE * borrowPrice / PRECISION);

        uint256 debtToRepay = debt > maxDebtRepayable ? maxDebtRepayable : debt;
        uint256 collateralSeized = (debtToRepay * borrowPrice * LIQUIDATION_INCENTIVE) / (collateralPrice * PRECISION);

        // Cap collateral seized at available amount
        if (collateralSeized > collateral) {
            collateralSeized = collateral;
        }

        // Transfer debt repayment from liquidator
        require(borrowToken.transferFrom(msg.sender, address(this), debtToRepay), "LendingPool: repay failed");

        // Update position state
        pos.borrowedAmount -= debtToRepay;
        pos.collateralAmount -= collateralSeized;
        totalBorrowed -= debtToRepay;
        totalDeposits -= collateralSeized;

        // Handle bad debt: if remaining debt exceeds remaining collateral value
        if (pos.borrowedAmount > 0) {
            uint256 remainingCollateralValue = (pos.collateralAmount * collateralPrice) / PRECISION;
            uint256 remainingDebtValue = (pos.borrowedAmount * borrowPrice) / PRECISION;
            if (remainingDebtValue > remainingCollateralValue) {
                uint256 badDebt = remainingDebtValue - remainingCollateralValue;
                badDebtReserve += badDebt;
                // Socialize: reduce total deposits accounting
                pos.borrowedAmount = 0;
                pos.collateralAmount = 0;
                totalBorrowed -= pos.borrowedAmount;
                totalDeposits -= pos.collateralAmount;
            }
        }

        // Transfer seized collateral to liquidator (includes incentive)
        require(collateralToken.transfer(msg.sender, collateralSeized), "LendingPool: transfer failed");
        emit Liquidated(user, msg.sender, debtToRepay);
    }

    function _isHealthy(address user) internal view returns (bool) {
        Position storage pos = positions[user];
        if (pos.borrowedAmount == 0) return true;

        uint256 collateralPrice = oracle.getPrice(address(collateralToken));
        uint256 borrowPrice = oracle.getPrice(address(borrowToken));

        // Validate oracle prices - revert on zero or invalid prices
        require(collateralPrice > 0, "LendingPool: invalid collateral price");
        require(borrowPrice > 0, "LendingPool: invalid borrow price");

        uint256 collateralValue = (pos.collateralAmount * collateralPrice) / PRECISION;
        uint256 borrowValue = (pos.borrowedAmount * borrowPrice) / PRECISION;

        // Position is healthy if collateral value >= borrow value * threshold
        // i.e., collateral ratio >= 125%. Below threshold means undercollateralized.
        return collateralValue >= (borrowValue * LIQUIDATION_THRESHOLD) / PRECISION;
    }

    function getPosition(address user) external view returns (uint256 collateral, uint256 debt) {
        Position storage pos = positions[user];
        return (pos.collateralAmount, pos.borrowedAmount);
    }
}
