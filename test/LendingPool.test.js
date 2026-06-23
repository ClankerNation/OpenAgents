const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("LendingPool", function () {
  let pool, owner, depositor, borrower, liquidator;
  let collateralToken, borrowToken, oracle;

  const COLLATERAL_PRICE = ethers.utils.parseUnits("2000", 18);
  const BORROW_PRICE = ethers.utils.parseUnits("1000", 18);

  beforeEach(async function () {
    [owner, depositor, borrower, liquidator] = await ethers.getSigners();

    const MockToken = await ethers.getContractFactory("MockERC20");
    collateralToken = await MockToken.deploy("Collateral", "COLL");
    borrowToken = await MockToken.deploy("Borrow", "BORROW");

    const MockOracle = await ethers.getContractFactory("MockPriceFeed");
    oracle = await MockOracle.deploy();

    const Pool = await ethers.getContractFactory("LendingPool");
    pool = await Pool.deploy(address(oracle), address(collateralToken), address(borrowToken));
    await pool.deployed();

    await collateralToken.mint(depositor.address, ethers.utils.parseEther("10000"));
    await collateralToken.mint(liquidator.address, ethers.utils.parseEther("5000"));
    await borrowToken.mint(liquidator.address, ethers.utils.parseEther("50000"));
  });

  describe("Flash Loan Liquidation", function () {
    it("should liquidate an underwater position via flash loan", async function () {
      await collateralToken.connect(borrower).mint(borrower.address, ethers.utils.parseEther("1000"));
      await collateralToken.connect(borrower).approve(pool.address, ethers.utils.parseEther("1000"));
      await pool.connect(borrower).deposit(ethers.utils.parseEther("1000"));
      await pool.connect(borrower).borrow(ethers.utils.parseEther("3000"));

      const liquidatorCollateralBefore = await collateralToken.balanceOf(liquidator.address);
      const liquidatorBorrowBefore = await borrowToken.balanceOf(liquidator.address);

      await pool.connect(liquidator).flashLiquidate(borrower.address);

      const liquidatorCollateralAfter = await collateralToken.balanceOf(liquidator.address);
      const liquidatorBorrowAfter = await borrowToken.balanceOf(liquidator.address);

      expect(liquidatorCollateralAfter).to.be.gt(liquidatorCollateralBefore);
      expect(liquidatorBorrowAfter).to.be.lt(liquidatorBorrowBefore);
    });

    it("should reject flash liquidation on healthy positions", async function () {
      await collateralToken.connect(borrower).mint(borrower.address, ethers.utils.parseEther("1000"));
      await collateralToken.connect(borrower).approve(pool.address, ethers.utils.parseEther("1000"));
      await pool.connect(borrower).deposit(ethers.utils.parseEther("1000"));
      await pool.connect(borrower).borrow(ethers.utils.parseEther("100"));

      await expect(pool.connect(liquidator).flashLiquidate(borrower.address))
        .to.be.revertedWith("Position healthy");
    });

    it("should emit FlashLoan event", async function () {
      await collateralToken.connect(borrower).mint(borrower.address, ethers.utils.parseEther("1000"));
      await collateralToken.connect(borrower).approve(pool.address, ethers.utils.parseEther("1000"));
      await pool.connect(borrower).deposit(ethers.utils.parseEther("1000"));
      await pool.connect(borrower).borrow(ethers.utils.parseEther("3000"));

      await expect(pool.connect(liquidator).flashLiquidate(borrower.address))
        .to.emit(pool, "FlashLoan");
    });
  });
});
