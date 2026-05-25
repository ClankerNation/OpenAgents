const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("LendingPool borrow caps", function () {
  let owner;
  let borrower;
  let user2;
  let user3;
  let user4;
  let user5;
  let other;
  let collateralToken;
  let borrowToken;
  let oracle;
  let lendingPool;

  const precision = ethers.parseEther("1");
  const poolLiquidity = ethers.parseEther("1000");
  const collateralAmount = ethers.parseEther("10000");

  beforeEach(async function () {
    [owner, borrower, user2, user3, user4, user5, other] = await ethers.getSigners();

    const AgentToken = await ethers.getContractFactory("AgentToken");
    collateralToken = await AgentToken.deploy("Collateral", "COL", ethers.parseEther("1000000"));
    borrowToken = await AgentToken.deploy("Borrow", "BRW", ethers.parseEther("1000000"));

    const MockPriceFeed = await ethers.getContractFactory("MockPriceFeed");
    oracle = await MockPriceFeed.deploy();
    await oracle.setPrice(await collateralToken.getAddress(), precision);
    await oracle.setPrice(await borrowToken.getAddress(), precision);

    const LendingPool = await ethers.getContractFactory("LendingPool");
    lendingPool = await LendingPool.deploy(
      await oracle.getAddress(),
      await collateralToken.getAddress(),
      await borrowToken.getAddress(),
    );

    await borrowToken.transfer(await lendingPool.getAddress(), poolLiquidity);
    await collateralToken.transfer(borrower.address, collateralAmount);
    for (const signer of [user2, user3, user4, user5, other]) {
      await collateralToken.transfer(signer.address, collateralAmount);
      await collateralToken.connect(signer).approve(await lendingPool.getAddress(), collateralAmount);
    }
    await collateralToken.connect(borrower).approve(await lendingPool.getAddress(), collateralAmount);
  });

  async function depositCollateral(signer = borrower) {
    await lendingPool.connect(signer).deposit(collateralAmount);
  }

  it("reverts when a borrow exceeds the asset cap", async function () {
    await depositCollateral();
    await expect(lendingPool.setMaxBorrowPerAsset(ethers.parseEther("100")))
      .to.emit(lendingPool, "MaxBorrowPerAssetUpdated");

    await expect(lendingPool.connect(borrower).borrow(ethers.parseEther("101"))).to.be.revertedWith(
      "Asset cap exceeded",
    );
  });

  it("prevents a single user from borrowing more than 25% of the pool", async function () {
    await depositCollateral();

    await lendingPool.connect(borrower).borrow(ethers.parseEther("250"));

    await expect(lendingPool.connect(borrower).borrow(1)).to.be.revertedWith(
      "User cap exceeded",
    );
  });

  it("blocks borrows that would push utilization above 95%", async function () {
    for (const signer of [borrower, user2, user3, user4, user5]) {
      await depositCollateral(signer);
    }

    await lendingPool.setMaxBorrowPerAsset(ethers.parseEther("2000"));
    const withinUserCap = ethers.parseEther("237.5");

    await lendingPool.connect(borrower).borrow(withinUserCap);
    await lendingPool.connect(user2).borrow(withinUserCap);
    await lendingPool.connect(user3).borrow(withinUserCap);
    await lendingPool.connect(user4).borrow(withinUserCap);

    await expect(lendingPool.connect(user5).borrow(ethers.parseEther("1"))).to.be.revertedWith(
      "Utilization too high",
    );
  });

  it("only lets the owner configure caps", async function () {
    await expect(
      lendingPool.connect(other).setMaxBorrowPerAsset(ethers.parseEther("100")),
    ).to.be.revertedWith("Not owner");

    await expect(lendingPool.setUserBorrowCapBps(2_000))
      .to.emit(lendingPool, "UserBorrowCapUpdated")
      .withArgs(2_500, 2_000);

    await expect(lendingPool.setMaxUtilizationBps(9_000))
      .to.emit(lendingPool, "MaxUtilizationUpdated")
      .withArgs(9_500, 9_000);

    await expect(lendingPool.setUserBorrowCapBps(2_501)).to.be.revertedWith("Invalid user cap");
    await expect(lendingPool.setMaxUtilizationBps(9_501)).to.be.revertedWith(
      "Invalid utilization",
    );
  });
});
