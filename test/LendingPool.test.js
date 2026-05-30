const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("LendingPool FlashLiquidation", function () {
  let collateralToken, borrowToken;
  let oracle;
  let lendingPool;
  let owner, borrower, liquidator;

  const PRECISION = ethers.parseEther("1");

  beforeEach(async function () {
    [owner, borrower, liquidator] = await ethers.getSigners();

    // 1. Deploy Mock Oracle
    const MockOracle = await ethers.getContractFactory("MockOracle");
    oracle = await MockOracle.deploy();
    await oracle.waitForDeployment();

    // 2. Deploy Tokens
    const StakingToken = await ethers.getContractFactory("StakingToken");
    collateralToken = await StakingToken.deploy();
    await collateralToken.waitForDeployment();

    borrowToken = await StakingToken.deploy();
    await borrowToken.waitForDeployment();

    // Set initial oracle prices:
    // Collateral token: $2.00
    // Borrow token: $1.00
    await oracle.setPrice(collateralToken.target, ethers.parseEther("2.0"));
    await oracle.setPrice(borrowToken.target, ethers.parseEther("1.0"));

    // 3. Deploy LendingPool
    const LendingPool = await ethers.getContractFactory("LendingPool");
    lendingPool = await LendingPool.deploy(
      oracle.target,
      collateralToken.target,
      borrowToken.target
    );
    await lendingPool.waitForDeployment();

    // Setup initial pool funding for borrowing
    // Mint borrow token to pool directly
    await borrowToken.mint(lendingPool.target, ethers.parseEther("10000"));
  });

  it("should allow borrower to deposit and borrow", async function () {
    // Deposit 100 collateral
    const collateralAmount = ethers.parseEther("100");
    await collateralToken.mint(borrower.address, collateralAmount);
    await collateralToken.connect(borrower).approve(lendingPool.target, collateralAmount);
    await lendingPool.connect(borrower).deposit(collateralAmount);

    // Borrow 100 borrow tokens (collateral value is 100 * 2.0 = $200. Max borrow is 200 / 1.5 = 133.3)
    const borrowAmount = ethers.parseEther("100");
    await lendingPool.connect(borrower).borrow(borrowAmount);

    const pos = await lendingPool.getPosition(borrower.address);
    expect(pos.collateral).to.equal(collateralAmount);
    expect(pos.debt).to.equal(borrowAmount);
  });

  it("should prevent flashLiquidate if borrower position is healthy", async function () {
    // Deposit 100 collateral
    const collateralAmount = ethers.parseEther("100");
    await collateralToken.mint(borrower.address, collateralAmount);
    await collateralToken.connect(borrower).approve(lendingPool.target, collateralAmount);
    await lendingPool.connect(borrower).deposit(collateralAmount);

    // Borrow 100
    const borrowAmount = ethers.parseEther("100");
    await lendingPool.connect(borrower).borrow(borrowAmount);

    // Try to liquidate
    await expect(
      lendingPool.connect(liquidator).flashLiquidate(borrower.address)
    ).to.be.revertedWith("Position healthy");
  });

  it("should allow flashLiquidate when position becomes unhealthy", async function () {
    // 1. Borrower setup
    const collateralAmount = ethers.parseEther("100");
    await collateralToken.mint(borrower.address, collateralAmount);
    await collateralToken.connect(borrower).approve(lendingPool.target, collateralAmount);
    await lendingPool.connect(borrower).deposit(collateralAmount);

    const borrowAmount = ethers.parseEther("100");
    await lendingPool.connect(borrower).borrow(borrowAmount);

    // 2. Drop collateral price from $2.00 to $1.40
    // Collateral value = 100 * 1.4 = $140.
    // Borrow value = 100 * 1.0 = $100.
    // Collateral ratio = 140 / 100 = 140%, which is below LIQUIDATION_THRESHOLD (150%)
    await oracle.setPrice(collateralToken.target, ethers.parseEther("1.4"));

    // 3. Liquidator has NO borrow tokens upfront
    const initialLiquidatorCollateral = await collateralToken.balanceOf(liquidator.address);
    expect(await borrowToken.balanceOf(liquidator.address)).to.equal(0);

    // Calculate expected variables:
    // debt = 100
    // fee = 100 * 0.0009 = 0.09
    // total repay in borrow token value = 100.09
    // collateralToRepay = (100.09 * $1.00) / $1.40 = 71.49285714... collateral tokens
    // profit = 100 - 71.49285714... = 28.5071428... collateral tokens
    const debt = ethers.parseEther("100");
    const fee = (debt * 9n) / 10000n;
    const borrowPrice = ethers.parseEther("1.0");
    const collateralPrice = ethers.parseEther("1.4");
    const expectedCollateralToRepay = ((debt + fee) * borrowPrice) / collateralPrice;
    const expectedProfit = collateralAmount - expectedCollateralToRepay;

    // 4. Perform flash liquidation
    const tx = await lendingPool.connect(liquidator).flashLiquidate(borrower.address);

    // Verify events emitted
    await expect(tx)
      .to.emit(lendingPool, "Liquidated")
      .withArgs(borrower.address, liquidator.address, debt);

    await expect(tx)
      .to.emit(lendingPool, "FlashLiquidated")
      .withArgs(borrower.address, liquidator.address, debt, fee, expectedProfit);

    // Verify borrower position is fully cleared
    const pos = await lendingPool.getPosition(borrower.address);
    expect(pos.collateral).to.equal(0);
    expect(pos.debt).to.equal(0);

    // Verify liquidator received the correct profit in collateralToken
    const finalLiquidatorCollateral = await collateralToken.balanceOf(liquidator.address);
    expect(finalLiquidatorCollateral - initialLiquidatorCollateral).to.equal(expectedProfit);
  });
});
