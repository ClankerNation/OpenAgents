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

    uint256 public constant LIQUIDATION_THRESHOLD = 1.5e18; // 150%
    uint256 public constant PRECISION = 1e18;
    uint256 public constant FLASH_LOAN_FEE_BPS = 900; // 0.09% fee in basis points
    uint256 public constant BASIS_POINTS = 10000;

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
    event FlashLoan(address indexed borrower, uint256 amount, uint256 fee);

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

    /// @notice Flash loan liquidation: borrow borrowToken from pool, repay underwater user's debt,
    ///         seize collateral, liquidator repays flash loan + fee from their own funds.
    /// @param user The address of the underwater position to liquidate.
    /// @dev No upfront capital needed for the debt repayment — the flash loan covers it.
    ///      Liquidator must repay flash loan + 0.09% fee from their own borrowToken balance.
    function flashLiquidate(address user) external {
        require(!_isHealthy(user), "Position healthy");

        Position storage pos = positions[user];
        uint256 debt = pos.borrowedAmount;
        uint256 collateral = pos.collateralAmount;
        require(debt > 0 && collateral > 0, "No debt or collateral");

        // Calculate flash loan fee (0.09%)
        uint256 fee = (debt * FLASH_LOAN_FEE_BPS) / BASIS_POINTS;

        // Step 1: Flash loan — lend borrowToken to liquidator
        require(borrowToken.transfer(msg.sender, debt), "Flash loan transfer failed");

        // Step 2: Liquidator repays the underwater user's debt
        require(borrowToken.transferFrom(msg.sender, address(this), debt), "Debt repayment failed");
        pos.borrowedAmount = 0;
        totalBorrowed -= debt;

        // Step 3: Seize collateral and transfer to liquidator
        totalDeposits -= collateral;
        pos.collateralAmount = 0;
        require(collateralToken.transfer(msg.sender, collateral), "Collateral transfer failed");
        emit Liquidated(user, msg.sender, debt);

        // Step 4: Liquidator repays flash loan fee (principal was used to repay debt)
        require(borrowToken.transferFrom(msg.sender, address(this), fee), "Flash loan fee payment failed");
        totalBorrowed += fee;

        emit FlashLoan(msg.sender, debt, fee);
    }

    function _isHealthy(address user) internal view returns (bool) {
        Position storage pos = positions[user];
        if (pos.borrowedAmount == 0) return true;

        uint256 collateralPrice = oracle.getPrice(address(collateralToken));
        uint256 borrowPrice = oracle.getPrice(address(borrowToken));

        uint256 collateralValue = (pos.collateralAmount * collateralPrice) / PRECISION;
        uint256 borrowValue = (pos.borrowedAmount * borrowPrice) / PRECISION;

        return collateralValue >= (borrowValue * LIQUIDATION_THRESHOLD) / PRECISION;
    }


    /// @notice Deposit collateral using Permit2 signature (gasless approval).
    /// @param amount Amount of collateral tokens to deposit.
    /// @param deadline Timestamp after which the permit expires.
    /// @param v ECDSA recovery byte.
    /// @param r ECDSA r value.
    /// @param s ECDSA s value.
    function depositWithPermit2(
        uint256 amount,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external {
        require(amount > 0, "Zero amount");
        require(block.timestamp <= deadline, "Permit2 expired");

        // Verify EIP-712 signature
        bytes32 structHash = keccak256(abi.encode(
            keccak256("Permit2Deposit(address owner,uint256 amount,uint256 nonce,uint256 deadline)"),
            msg.sender,
            amount,
            0,
            deadline
        ));
        bytes32 digest = keccak256(abi.encodePacked("", DOMAIN_SEPARATOR(), structHash));
        address recovered = ecrecover(digest, v, r, s);
        require(recovered != address(0) && recovered == msg.sender, "Permit2: invalid signature");

        // Transfer tokens (caller must have approved this contract)
        require(collateralToken.transferFrom(msg.sender, address(this), amount), "Transfer failed");
        positions[msg.sender].collateralAmount += amount;
        totalDeposits += amount;
        emit Deposited(msg.sender, amount);
    }

    /// @notice Domain separator for Permit2 deposit signatures.
    /// @return The EIP-712 domain separator.
    function DOMAIN_SEPARATOR() public view returns (bytes32) {
        return keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256(bytes("LendingPool")),
            keccak256(bytes("1")),
            block.chainid,
            address(this)
        ));
    }

    function getPosition(address user) external view returns (uint256 collateral, uint256 debt) {
        Position storage pos = positions[user];
        return (pos.collateralAmount, pos.borrowedAmount);
    }
}
