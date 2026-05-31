// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "../lending/LendingPool.sol";

contract MockToken is ERC20 {
    constructor(string memory name, string memory symbol) ERC20(name, symbol) {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

contract MockOracle is IPriceFeed {
    mapping(address => uint256) public prices;

    function setPrice(address token, uint256 price) external {
        prices[token] = price;
    }

    function getPrice(address token) external view returns (uint256) {
        return prices[token];
    }
}

contract MockFlashLiquidator is IFlashLiquidator {
    LendingPool public pool;
    IERC20 public borrowToken;
    bool public shouldRevert;

    constructor(address _pool, address _borrowToken) {
        pool = LendingPool(_pool);
        borrowToken = IERC20(_borrowToken);
    }

    function setShouldRevert(bool _shouldRevert) external {
        shouldRevert = _shouldRevert;
    }

    function executeOperation(
        address collateralToken,
        address _borrowToken,
        uint256 debt,
        uint256 collateral,
        uint256 fee,
        bytes calldata params
    ) external returns (bool) {
        require(msg.sender == address(pool), "Untrusted caller");
        require(!shouldRevert, "Simulated failure");

        // The liquidator uses the received collateral to buy borrowToken 
        // to repay the debt + fee.
        // We will just mint the required borrowToken to simulate a profitable swap.
        uint256 amountToRepay = debt + fee;
        
        // Let's assume the liquidator swaps some collateral to get exactly `amountToRepay`.
        // So we mint `amountToRepay` borrowToken to this contract and approve the pool.
        MockToken(address(borrowToken)).mint(address(this), amountToRepay);
        borrowToken.approve(address(pool), amountToRepay);

        return true;
    }

    function liquidate(address user) external {
        pool.flashLiquidate(user, "");
    }
}
