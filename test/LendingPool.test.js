const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("LendingPool Flash Liquidation", function () {
    let pool, collateralToken, borrowToken, oracle, liquidator;
    let owner, user, user2;

    const PRECISION = ethers.parseEther("1");
    const DEPOSIT_AMOUNT = ethers.parseEther("1000"); // 1000 collateral
    const BORROW_AMOUNT = ethers.parseEther("500"); // 500 borrowToken

    beforeEach(async function () {
        [owner, user, user2] = await ethers.getSigners();

        const MockToken = await ethers.getContractFactory("MockToken");
        collateralToken = await MockToken.deploy("Collateral", "COL");
        borrowToken = await MockToken.deploy("Borrow", "BOR");

        const MockOracle = await ethers.getContractFactory("MockOracle");
        oracle = await MockOracle.deploy();

        const LendingPool = await ethers.getContractFactory("LendingPool");
        pool = await LendingPool.deploy(await oracle.getAddress(), await collateralToken.getAddress(), await borrowToken.getAddress());

        const MockFlashLiquidator = await ethers.getContractFactory("MockFlashLiquidator");
        liquidator = await MockFlashLiquidator.deploy(await pool.getAddress(), await borrowToken.getAddress());

        // Set oracle prices (1 COL = 1 BOR)
        await oracle.setPrice(await collateralToken.getAddress(), PRECISION);
        await oracle.setPrice(await borrowToken.getAddress(), PRECISION);

        // Setup user position
        await collateralToken.mint(user.address, DEPOSIT_AMOUNT);
        await collateralToken.connect(user).approve(await pool.getAddress(), DEPOSIT_AMOUNT);
        await pool.connect(user).deposit(DEPOSIT_AMOUNT);

        // Mint borrow token to pool so user can borrow
        await borrowToken.mint(await pool.getAddress(), ethers.parseEther("10000"));
        await pool.connect(user).borrow(BORROW_AMOUNT);
    });

    it("should revert flash liquidation if position is healthy", async function () {
        await expect(liquidator.liquidate(user.address)).to.be.revertedWith("Position healthy");
    });

    it("should allow profitable flash liquidation when undercollateralized", async function () {
        // Drop collateral price so collateral value < 150% of borrow value
        // Original borrow value = 500. Needs 750 collateral value to be healthy.
        // Current collateral is 1000. Price = 1. Value = 1000.
        // Let's drop collateral price to 0.5.
        await oracle.setPrice(await collateralToken.getAddress(), ethers.parseEther("0.5"));

        // Now collateral value is 500, borrow value is 500. Health < 150%. Unhealthy.
        
        const debt = await pool.getPosition(user.address).then(p => p.debt);
        const collateral = await pool.getPosition(user.address).then(p => p.collateral);
        
        expect(debt).to.equal(BORROW_AMOUNT);
        expect(collateral).to.equal(DEPOSIT_AMOUNT);

        const fee = (debt * 9n) / 10000n; // 0.09% fee

        // Before liquidation
        const liquidatorCollateralBalanceBefore = await collateralToken.balanceOf(await liquidator.getAddress());

        // Liquidate
        await expect(liquidator.liquidate(user.address))
            .to.emit(pool, "Liquidated")
            .withArgs(user.address, await liquidator.getAddress(), debt);

        // Check user position is 0
        const posAfter = await pool.getPosition(user.address);
        expect(posAfter.collateral).to.equal(0n);
        expect(posAfter.debt).to.equal(0n);

        // Check liquidator profit (they received all collateral, and they minted borrowToken to repay)
        const liquidatorCollateralBalanceAfter = await collateralToken.balanceOf(await liquidator.getAddress());
        expect(liquidatorCollateralBalanceAfter).to.equal(liquidatorCollateralBalanceBefore + collateral);
    });

    it("should revert if liquidator fails to repay loan + fee", async function () {
        await oracle.setPrice(await collateralToken.getAddress(), ethers.parseEther("0.5"));
        
        // Setup liquidator to revert its executeOperation
        await liquidator.setShouldRevert(true);

        await expect(liquidator.liquidate(user.address)).to.be.revertedWith("Simulated failure");
    });

    it("should calculate and collect exact fee", async function () {
        await oracle.setPrice(await collateralToken.getAddress(), ethers.parseEther("0.5"));

        const debt = BORROW_AMOUNT;
        const fee = (debt * 9n) / 10000n; // 0.09% fee

        const totalFeesBefore = await pool.totalFeesCollected();

        await liquidator.liquidate(user.address);

        const totalFeesAfter = await pool.totalFeesCollected();
        expect(totalFeesAfter).to.equal(totalFeesBefore + fee);
    });
});
