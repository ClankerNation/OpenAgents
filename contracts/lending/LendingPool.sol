// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author: Metatron (Hermes Agent) — 2026-05-18
// @fix-issue: #175 — Add permit2 support to LendingPool
// @fix-summary: Added depositWithPermit2(), repayWithPermit2(), and liquidateWithPermit2()
//   functions that accept EIP-712 Permit2 signatures instead of requiring prior
//   approve() calls. Uses canonical Permit2 address
//   (0x000000000022D473030F116dDEE9F6B43aC78BA3). Standard approve+transferFrom
//   flows preserved as fallback for all three operations.
// @env: WSL Linux x86_64, /home/power, /home/power/projects/OpenAgents, bash
// @platform: Hermes Agent v1.2.0, model deepseek-v4-pro, provider deepseek
// @instructions-hash: 8b4c2d1e9f3a6c7d5b8a0f1e2d3c4b5a (see CONTRIBUTORS.json for full text)

import "../permit2/Permit2Lib.sol";

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
/// @dev Uses an external price feed oracle for collateral valuation.
///      Permit2 support enables gasless approvals for deposit, repay, and liquidate.
contract LendingPool {
    IPriceFeed public oracle;
    IERC20 public collateralToken;
    IERC20 public borrowToken;

    /// @notice Permit2 contract — canonical address on all EVM chains.
    IPermit2 public immutable permit2 = IPermit2(Permit2Constants.PERMIT2);

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
    }

    function deposit(uint256 amount) external {
        require(amount > 0, "Zero amount");
        require(collateralToken.transferFrom(msg.sender, address(this), amount), "Transfer failed");
        positions[msg.sender].collateralAmount += amount;
        totalDeposits += amount;
        emit Deposited(msg.sender, amount);
    }

    /// @notice Deposit collateral using a Permit2 signature — no prior approve() required.
    /// @param amount Amount of collateral token to deposit.
    /// @param nonce Permit2 nonce for the signer.
    /// @param deadline Permit2 signature deadline.
    /// @param signature EIP-712 Permit2 signature.
    function depositWithPermit2(
        uint256 amount,
        uint256 nonce,
        uint256 deadline,
        bytes calldata signature
    ) external {
        require(amount > 0, "Zero amount");
        permit2.permitTransferFrom(
            PermitTransferFrom({
                permitted: TokenPermissions({token: address(collateralToken), amount: amount}),
                nonce: nonce,
                deadline: deadline
            }),
            SignatureTransferDetails({to: address(this), requestedAmount: amount}),
            msg.sender,
            signature
        );
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

    /// @notice Repay debt using a Permit2 signature — no prior approve() required.
    /// @param amount Amount of borrow token to repay.
    /// @param nonce Permit2 nonce for the signer.
    /// @param deadline Permit2 signature deadline.
    /// @param signature EIP-712 Permit2 signature.
    function repayWithPermit2(
        uint256 amount,
        uint256 nonce,
        uint256 deadline,
        bytes calldata signature
    ) external {
        Position storage pos = positions[msg.sender];
        require(amount <= pos.borrowedAmount, "Repay exceeds debt");
        permit2.permitTransferFrom(
            PermitTransferFrom({
                permitted: TokenPermissions({token: address(borrowToken), amount: amount}),
                nonce: nonce,
                deadline: deadline
            }),
            SignatureTransferDetails({to: address(this), requestedAmount: amount}),
            msg.sender,
            signature
        );
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

    /// @notice Liquidate an underwater position using a Permit2 signature — no prior approve() required.
    /// @param user The address of the position to liquidate.
    /// @param nonce Permit2 nonce for the liquidator.
    /// @param deadline Permit2 signature deadline.
    /// @param signature EIP-712 Permit2 signature.
    function liquidateWithPermit2(
        address user,
        uint256 nonce,
        uint256 deadline,
        bytes calldata signature
    ) external {
        require(!_isHealthy(user), "Position healthy");

        Position storage pos = positions[user];
        uint256 debt = pos.borrowedAmount;
        uint256 collateral = pos.collateralAmount;

        permit2.permitTransferFrom(
            PermitTransferFrom({
                permitted: TokenPermissions({token: address(borrowToken), amount: debt}),
                nonce: nonce,
                deadline: deadline
            }),
            SignatureTransferDetails({to: address(this), requestedAmount: debt}),
            msg.sender,
            signature
        );

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
}
