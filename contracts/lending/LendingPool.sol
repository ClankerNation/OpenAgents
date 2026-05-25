// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
 * Contributor metadata:
 * Agent: Codex
 * Timestamp: 2026-05-25T11:06:35Z
 * Runtime: os=Windows, arch=x64,
 * working_dir=C:\Users\tupm96\Desktop\bounty\OpenAgents, shell=powershell
 * Private platform, system, and developer instructions are not disclosed.
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
/// @notice Collateralized lending pool supporting deposit, borrow, repay, and liquidation
/// @dev Uses an external price feed oracle for collateral valuation
contract LendingPool {
    IPriceFeed public oracle;
    IERC20 public collateralToken;
    IERC20 public borrowToken;
    address public owner;

    // BUG: Liquidation threshold hardcoded to 150% (1.5e18) but the check uses >=,
    // meaning positions at exactly 150% collateral ratio are liquidatable when they
    // should be healthy — threshold should be lower (e.g., 125%) or check should use <
    uint256 public constant LIQUIDATION_THRESHOLD = 1.5e18; // 150%
    uint256 public constant PRECISION = 1e18;
    uint256 public constant BPS_DENOMINATOR = 10_000;
    uint256 public constant MAX_USER_BORROW_CAP_BPS = 2_500; // 25%
    uint256 public constant MAX_ALLOWED_UTILIZATION_BPS = 9_500; // 95%
    uint256 public maxBorrowPerAsset;
    uint256 public userBorrowCapBps;
    uint256 public maxUtilizationBps;

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
    event MaxBorrowPerAssetUpdated(uint256 oldCap, uint256 newCap);
    event UserBorrowCapUpdated(uint256 oldCapBps, uint256 newCapBps);
    event MaxUtilizationUpdated(uint256 oldUtilizationBps, uint256 newUtilizationBps);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(address _oracle, address _collateralToken, address _borrowToken) {
        oracle = IPriceFeed(_oracle);
        collateralToken = IERC20(_collateralToken);
        borrowToken = IERC20(_borrowToken);
        owner = msg.sender;
        maxBorrowPerAsset = type(uint256).max;
        userBorrowCapBps = MAX_USER_BORROW_CAP_BPS;
        maxUtilizationBps = MAX_ALLOWED_UTILIZATION_BPS;
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
        _validateBorrowCaps(msg.sender, amount);

        positions[msg.sender].borrowedAmount += amount;
        totalBorrowed += amount;
        require(_isHealthy(msg.sender), "Undercollateralized");

        require(borrowToken.transfer(msg.sender, amount), "Transfer failed");
        emit Borrowed(msg.sender, amount);
    }

    function setMaxBorrowPerAsset(uint256 newCap) external onlyOwner {
        uint256 oldCap = maxBorrowPerAsset;
        maxBorrowPerAsset = newCap;
        emit MaxBorrowPerAssetUpdated(oldCap, newCap);
    }

    function setUserBorrowCapBps(uint256 newCapBps) external onlyOwner {
        require(newCapBps > 0 && newCapBps <= MAX_USER_BORROW_CAP_BPS, "Invalid user cap");
        uint256 oldCapBps = userBorrowCapBps;
        userBorrowCapBps = newCapBps;
        emit UserBorrowCapUpdated(oldCapBps, newCapBps);
    }

    function setMaxUtilizationBps(uint256 newUtilizationBps) external onlyOwner {
        require(
            newUtilizationBps > 0 && newUtilizationBps <= MAX_ALLOWED_UTILIZATION_BPS,
            "Invalid utilization"
        );
        uint256 oldUtilizationBps = maxUtilizationBps;
        maxUtilizationBps = newUtilizationBps;
        emit MaxUtilizationUpdated(oldUtilizationBps, newUtilizationBps);
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

    function getPosition(address user) external view returns (uint256 collateral, uint256 debt) {
        Position storage pos = positions[user];
        return (pos.collateralAmount, pos.borrowedAmount);
    }

    function getBorrowPoolSize() public view returns (uint256) {
        return borrowToken.balanceOf(address(this)) + totalBorrowed;
    }

    function _validateBorrowCaps(address user, uint256 amount) internal view {
        uint256 poolSize = getBorrowPoolSize();
        require(amount <= borrowToken.balanceOf(address(this)), "Insufficient liquidity");

        uint256 newTotalBorrowed = totalBorrowed + amount;
        require(newTotalBorrowed <= maxBorrowPerAsset, "Asset cap exceeded");

        uint256 newUserBorrowed = positions[user].borrowedAmount + amount;
        require(
            newUserBorrowed <= (poolSize * userBorrowCapBps) / BPS_DENOMINATOR,
            "User cap exceeded"
        );

        require(
            (newTotalBorrowed * BPS_DENOMINATOR) / poolSize <= maxUtilizationBps,
            "Utilization too high"
        );
    }
}
