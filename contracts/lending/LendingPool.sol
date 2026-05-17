// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../oracle/TWAPOracle.sol";

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
/// @dev Uses an external price feed oracle and TWAP for price validation
/// @contributor opencode-gaotax2006
/// @platform You are opencode, an interactive CLI tool...
/// @runtime os=win32 arch=x64 workingdir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
/// @date 2026-05-18T00:00:00Z
contract LendingPool {
    IPriceFeed public oracle;
    TWAPOracle public twapOracle;
    IERC20 public collateralToken;
    IERC20 public borrowToken;

    uint256 public constant LIQUIDATION_THRESHOLD = 1.5e18;
    uint256 public constant PRECISION = 1e18;
    uint256 public constant MAX_PRICE_DEVIATION = 5e16;

    uint256 public constant BAD_DEBT_RESERVE = 1e17;

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
    event Liquidated(address indexed user, address indexed liquidator, uint256 debtRepaid, uint256 incentive);

    constructor(address _oracle, address _twapOracle, address _collateralToken, address _borrowToken) {
        oracle = IPriceFeed(_oracle);
        twapOracle = TWAPOracle(_twapOracle);
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

        uint256 spotPrice = twapOracle.getLatestPrice();
        uint256 twapPrice = twapOracle.getTWAP();
        require(spotPrice > 0 && twapPrice > 0, "Invalid price");

        uint256 deviation = spotPrice > twapPrice
            ? ((spotPrice - twapPrice) * PRECISION) / twapPrice
            : ((twapPrice - spotPrice) * PRECISION) / spotPrice;
        require(deviation <= MAX_PRICE_DEVIATION, "Price deviation too high");

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

        uint256 collateralPrice = _getValidPrice(address(collateralToken));
        uint256 borrowPrice = _getValidPrice(address(borrowToken));

        uint256 collateralValue = (collateral * collateralPrice) / PRECISION;
        uint256 debtValue = (debt * borrowPrice) / PRECISION;

        uint256 incentive = (debt * BAD_DEBT_RESERVE) / PRECISION;
        if (collateralValue < debtValue) {
            incentive = 0;
        }

        require(borrowToken.transferFrom(msg.sender, address(this), debt), "Transfer failed");

        pos.borrowedAmount = 0;
        pos.collateralAmount = 0;
        totalBorrowed -= debt;
        totalDeposits -= collateral;

        uint256 liquidatorCollateral = collateral + incentive;
        require(collateralToken.transfer(msg.sender, liquidatorCollateral), "Transfer failed");
        emit Liquidated(user, msg.sender, debt, incentive);
    }

    function _getValidPrice(address token) internal view returns (uint256) {
        uint256 price = oracle.getPrice(token);
        require(price > 0, "Zero price");
        return price;
    }

    function _isHealthy(address user) internal view returns (bool) {
        Position storage pos = positions[user];
        if (pos.borrowedAmount == 0) return true;

        uint256 collateralPrice = _getValidPrice(address(collateralToken));
        uint256 borrowPrice = _getValidPrice(address(borrowToken));

        uint256 collateralValue = (pos.collateralAmount * collateralPrice) / PRECISION;
        uint256 borrowValue = (pos.borrowedAmount * borrowPrice) / PRECISION;

        return collateralValue >= (borrowValue * LIQUIDATION_THRESHOLD) / PRECISION;
    }

    function getPosition(address user) external view returns (uint256 collateral, uint256 debt) {
        Position storage pos = positions[user];
        return (pos.collateralAmount, pos.borrowedAmount);
    }
}
