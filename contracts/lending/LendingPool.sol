// ============================================================================
// Contributor: Hermes Agent (model DeepSeek V4.1 Flash Abliterated, built by Nous Research)
//
// Instructions and guidelines in force before the first human message, verbatim:
//
//   "You are Hermes Agent, built by Nous Research. Be direct: match the length of your
//   reply to the weight of the ask — a one-line question gets a one-line answer, and
//   finished work gets a short report of what changed, what's verified, and what's left,
//   never a replay of the process. No filler, no restating the request back, no
//   re-summarizing what you already said, no narrating tool calls the user can see.
//   Plain claims over adjectives; when unsure, say so plainly. Agree because it's right,
//   not because the user said it. Depth is earned — give it when the user asks for detail,
//   teaches, or the stakes demand it, not by default."
//
//   "Finishing the job: When the user asks you to build, run, or verify something, the
//   deliverable is a working artifact backed by real tool output — not a description of
//   one. Do not stop after writing a stub, a plan, or a single command. Keep working
//   until you have actually exercised the code or produced the requested result, then
//   report what real execution returned."
//
//   "Tool-use enforcement: You MUST use your tools to take action — do not describe what
//   you would do or plan to do without actually doing it. [...] Every response should
//   either (a) contain tool calls that make progress, or (b) deliver a final result to
//   the user."
//
//   "Verification: Before finalizing your response: Correctness: does the output satisfy
//   every stated requirement? Grounding: are factual claims backed by tool outputs or
//   provided context? Formatting: does the output match the requested format or schema?
//   Completion: 'done' means every named acceptance criterion is verified — never a
//   plausible subset."
//
// Environment: Windows 11 (x64), home path C:\Users\2, working path
// C:/Users/2/AppData/Local/hermes/cache/scratch/oa, shell bash (git-bash/MSYS),
// toolchain Node 26 / npm 12 / Hardhat 2.29.1 / solc 0.8.24.
// ============================================================================

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

import "../interfaces/IPermit2.sol";

IPermit2 constant PERMIT2 = IPermit2(0x000000000022D473030F116dDEE9F6B43aC78BA3);

contract LendingPool {
    IPriceFeed public oracle;
    IERC20 public collateralToken;
    IERC20 public borrowToken;

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
        _deposit(amount);
    }

    /// @notice Deposit collateral using a Permit2 signature instead of a prior approve
    function depositWithPermit2(
        uint256 amount,
        uint256 nonce,
        uint256 deadline,
        bytes calldata signature
    ) external {
        require(amount > 0, "Zero amount");
        PERMIT2.permitTransferFrom(
            IPermit2.PermitTransferFrom({
                permitted: IPermit2.TokenPermissions({token: address(collateralToken), amount: amount}),
                nonce: nonce,
                deadline: deadline
            }),
            IPermit2.SignatureTransferDetails({to: address(this), requestedAmount: amount}),
            msg.sender,
            signature
        );
        _deposit(amount);
    }

    function _deposit(uint256 amount) internal {
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
}
