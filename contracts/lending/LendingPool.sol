// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
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
    address public owner;

    // Borrow caps
    uint256 public maxBorrowPerAsset;      // Max total borrows for this asset
    uint256 public maxBorrowPerUserPct;    // Max % of pool a single user can borrow (basis points, e.g., 2500 = 25%)
    uint256 public maxUtilizationPct;      // Max utilization before blocking new borrows (basis points, e.g., 9500 = 95%)

    event CapsUpdated(uint256 maxBorrowPerAsset, uint256 maxBorrowPerUserPct, uint256 maxUtilizationPct);

    // BUG: Liquidation threshold hardcoded to 150% (1.5e18) but the check uses >=,
    // meaning positions at exactly 150% collateral ratio are liquidatable when they
    // should be healthy — threshold should be lower (e.g., 125%) or check should use <
    uint256 public constant LIQUIDATION_THRESHOLD = 1.5e18; // 150%
    uint256 public constant PRECISION = 1e18;

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
        owner = msg.sender;
        maxBorrowPerAsset = type(uint256).max; // No cap by default
        maxBorrowPerUserPct = 2500;            // 25% per user
        maxUtilizationPct = 9500;              // 95% max utilization
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

        // Check per-asset borrow cap
        require(totalBorrowed + amount <= maxBorrowPerAsset, "Exceeds asset borrow cap");

        // Check per-user borrow cap (max % of total pool)
        uint256 poolBalance = borrowToken.balanceOf(address(this));
        uint256 poolTotal = poolBalance + totalBorrowed;
        if (poolTotal > 0) {
            uint256 userNewDebt = positions[msg.sender].borrowedAmount + amount;
            require(userNewDebt * 10000 <= poolTotal * maxBorrowPerUserPct, "Exceeds per-user borrow cap");
        }

        // Check utilization cap
        if (poolTotal > 0) {
            uint256 newUtilization = (totalBorrowed + amount) * 10000 / poolTotal;
            require(newUtilization <= maxUtilizationPct, "Exceeds max utilization");
        }

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

    // BUG: No bad debt handling — if collateral value drops below debt value,
    // liquidator repays debt but received collateral is worth less, creating a
    // protocol loss that is never socialized or covered by a reserve
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

    function _isHealthy(address user) internal view returns (bool) {
        Position storage pos = positions[user];
        if (pos.borrowedAmount == 0) return true;

        // BUG: Oracle price not validated — getPrice could return 0 or stale data,
        // making all positions appear healthy (0 * anything = 0) or unhealthy
        uint256 collateralPrice = oracle.getPrice(address(collateralToken));
        uint256 borrowPrice = oracle.getPrice(address(borrowToken));

        uint256 collateralValue = (pos.collateralAmount * collateralPrice) / PRECISION;
        uint256 borrowValue = (pos.borrowedAmount * borrowPrice) / PRECISION;

        return collateralValue >= (borrowValue * LIQUIDATION_THRESHOLD) / PRECISION;
    }

    /// @notice Update borrow caps. Only callable by owner.
    function setCaps(
        uint256 _maxBorrowPerAsset,
        uint256 _maxBorrowPerUserPct,
        uint256 _maxUtilizationPct
    ) external {
        require(msg.sender == owner, "Not owner");
        require(_maxBorrowPerUserPct <= 10000, "Invalid user cap");
        require(_maxUtilizationPct <= 10000, "Invalid utilization cap");
        maxBorrowPerAsset = _maxBorrowPerAsset;
        maxBorrowPerUserPct = _maxBorrowPerUserPct;
        maxUtilizationPct = _maxUtilizationPct;
        emit CapsUpdated(_maxBorrowPerAsset, _maxBorrowPerUserPct, _maxUtilizationPct);
    }

    function getPosition(address user) external view returns (uint256 collateral, uint256 debt) {
        Position storage pos = positions[user];
        return (pos.collateralAmount, pos.borrowedAmount);
    }
}
