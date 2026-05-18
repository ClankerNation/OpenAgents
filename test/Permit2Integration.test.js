const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Permit2 Integration", function () {
  let mockPermit2;
  let stakingToken, rewardToken, ammTokenA, ammTokenB, collateralToken, borrowToken;
  let stakingRewards, ammPool, lendingPool;
  let owner, user;

  const PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3";

  before(async function () {
    [owner, user] = await ethers.getSigners();

    // Deploy MockPermit2 at the canonical Permit2 address
    const MockPermit2Factory = await ethers.getContractFactory("MockPermit2");
    mockPermit2 = await MockPermit2Factory.deploy();
    await mockPermit2.waitForDeployment();

    // Set bytecode at canonical Permit2 address so contracts can resolve it
    await ethers.provider.send("hardhat_setCode", [
      PERMIT2_ADDRESS,
      await ethers.provider.send("eth_getCode", [await mockPermit2.getAddress()])
    ]);

    // Deploy tokens
    const ERC20Factory = await ethers.getContractFactory("StakingToken");
    stakingToken = await ERC20Factory.deploy();
    await stakingToken.waitForDeployment();
    rewardToken = await ERC20Factory.deploy();
    await rewardToken.waitForDeployment();
    ammTokenA = await ERC20Factory.deploy();
    await ammTokenA.waitForDeployment();
    ammTokenB = await ERC20Factory.deploy();
    await ammTokenB.waitForDeployment();
    collateralToken = await ERC20Factory.deploy();
    await collateralToken.waitForDeployment();
    borrowToken = await ERC20Factory.deploy();
    await borrowToken.waitForDeployment();

    // Deploy contracts (they'll resolve permit2 from canonical address)
    const StakingRewardsFactory = await ethers.getContractFactory("StakingRewards");
    stakingRewards = await StakingRewardsFactory.deploy(
      await stakingToken.getAddress(),
      await rewardToken.getAddress()
    );
    await stakingRewards.waitForDeployment();

    const AMMPoolFactory = await ethers.getContractFactory("AMMPool");
    ammPool = await AMMPoolFactory.deploy(
      await ammTokenA.getAddress(),
      await ammTokenB.getAddress()
    );
    await ammPool.waitForDeployment();

    // Mint tokens for testing
    await stakingToken.mint(user.address, ethers.parseEther("1000"));
    await ammTokenA.mint(user.address, ethers.parseEther("1000"));
    await ammTokenB.mint(user.address, ethers.parseEther("1000"));
    await rewardToken.mint(await stakingRewards.getAddress(), ethers.parseEther("10000"));
    await collateralToken.mint(user.address, ethers.parseEther("1000"));
    await borrowToken.mint(user.address, ethers.parseEther("1000"));
  });

  describe("StakingRewards — permit2 stake", function () {
    it("should stake tokens with Permit2 signature", async function () {
      const amount = ethers.parseEther("100");

      // Standard approve must NOT be required — permit2 handles transfer
      // First verify user has tokens
      const userBalance = await stakingToken.balanceOf(user.address);
      expect(userBalance).to.be.gte(amount);

      // Directly approve MockPermit2 to spend user's tokens (simulating what
      // a real Permit2 signature would authorize)
      await stakingToken.connect(user).approve(PERMIT2_ADDRESS, amount);

      // Call stakeWithPermit2 — MockPermit2 will execute the transfer
      const deadline = Math.floor(Date.now() / 1000) + 3600;
      await stakingRewards.connect(user).stakeWithPermit2(
        amount,
        0, // nonce
        deadline,
        "0x" // dummy signature — MockPermit2 ignores it
      );

      const staked = await stakingRewards.balanceOf(user.address);
      expect(staked).to.equal(amount);
    });

    it("should support standard approve+stake as fallback", async function () {
      // Use a fresh amount
      const amount = ethers.parseEther("50");
      await stakingToken.connect(user).approve(
        await stakingRewards.getAddress(),
        amount
      );
      await stakingRewards.connect(user).stake(amount);

      const staked = await stakingRewards.balanceOf(user.address);
      // previous test staked 100, now 50 more = 150
      expect(staked).to.equal(ethers.parseEther("150"));
    });
  });

  describe("AMMPool — permit2 swap", function () {
    let lpTokens;

    before(async function () {
      // Add liquidity to the pool first (as owner)
      await ammTokenA.mint(owner.address, ethers.parseEther("10000"));
      await ammTokenB.mint(owner.address, ethers.parseEther("10000"));
      await ammTokenA.connect(owner).approve(await ammPool.getAddress(), ethers.parseEther("1000"));
      await ammTokenB.connect(owner).approve(await ammPool.getAddress(), ethers.parseEther("1000"));
      const tx = await ammPool.connect(owner).addLiquidity(
        ethers.parseEther("1000"),
        ethers.parseEther("1000")
      );
    });

    it("should swap tokens with Permit2 signature", async function () {
      const amountIn = ethers.parseEther("10");

      // Get expected output
      const [resA] = await ammPool.getReserves();
      // Approve MockPermit2 for the swap
      await ammTokenA.connect(user).approve(PERMIT2_ADDRESS, amountIn);

      const deadline = Math.floor(Date.now() / 1000) + 3600;
      await ammPool.connect(user).swapWithPermit2(
        await ammTokenA.getAddress(),
        amountIn,
        0, // minAmountOut = 0 for test
        0, // nonce
        deadline,
        "0x" // dummy signature
      );

      // Verify user received tokens
      const tokenBBalance = await ammTokenB.balanceOf(user.address);
      expect(tokenBBalance).to.be.gt(0);
    });

    it("should support standard approve+swap as fallback", async function () {
      const amountIn = ethers.parseEther("10");
      await ammTokenA.connect(user).approve(await ammPool.getAddress(), amountIn);
      await ammPool.connect(user).swap(
        await ammTokenA.getAddress(),
        amountIn,
        0
      );

      const tokenBBalance = await ammTokenB.balanceOf(user.address);
      expect(tokenBBalance).to.be.gt(0);
    });
  });

  describe("LendingPool — permit2 deposit", function () {
    // Deploy a minimal oracle for LendingPool
    let lendingPoolDeploy, priceFeed;

    before(async function () {
      // Deploy mock price feed
      const MockPriceFeed = await ethers.getContractFactory("MockPriceFeed");
      priceFeed = await MockPriceFeed.deploy();
      await priceFeed.waitForDeployment();

      const LendingPoolFactory = await ethers.getContractFactory("LendingPool");
      lendingPool = await LendingPoolFactory.deploy(
        await priceFeed.getAddress(),
        await collateralToken.getAddress(),
        await borrowToken.getAddress()
      );
      await lendingPool.waitForDeployment();

      // Fund the pool with borrow token for testing
      await borrowToken.mint(await lendingPool.getAddress(), ethers.parseEther("10000"));
    });

    it("should deposit collateral with Permit2 signature", async function () {
      const amount = ethers.parseEther("100");
      await collateralToken.connect(user).approve(PERMIT2_ADDRESS, amount);

      const deadline = Math.floor(Date.now() / 1000) + 3600;
      await lendingPool.connect(user).depositWithPermit2(
        amount,
        0,
        deadline,
        "0x"
      );

      const [collateral] = await lendingPool.getPosition(user.address);
      expect(collateral).to.equal(amount);
    });

    it("should support standard approve+deposit as fallback", async function () {
      const amount = ethers.parseEther("50");
      await collateralToken.connect(user).approve(
        await lendingPool.getAddress(),
        amount
      );
      await lendingPool.connect(user).deposit(amount);

      const [collateral] = await lendingPool.getPosition(user.address);
      expect(collateral).to.equal(ethers.parseEther("150"));
    });
  });

  describe("Permit2 signature validation (MockPermit2)", function () {
    it("should reject expired deadlines", async function () {
      const amount = ethers.parseEther("10");
      await stakingToken.connect(user).approve(PERMIT2_ADDRESS, amount);

      const expiredDeadline = Math.floor(Date.now() / 1000) - 3600; // 1 hour ago
      await expect(
        stakingRewards.connect(user).stakeWithPermit2(
          amount,
          0,
          expiredDeadline,
          "0x"
        )
      ).to.be.revertedWith("MockPermit2: expired");
    });

    it("should reject zero-amount stakes", async function () {
      await expect(
        stakingRewards.connect(user).stakeWithPermit2(
          0,
          0,
          Math.floor(Date.now() / 1000) + 3600,
          "0x"
        )
      ).to.be.revertedWith("Cannot stake 0");
    });
  });
});
