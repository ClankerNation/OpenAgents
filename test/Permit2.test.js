const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Permit2 Integration", function () {
  let stakingToken, rewardToken;
  let stakingRewards, ammPool, lendingPool, priceFeed;
  let owner, user1, user2;

  const PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3";

  before(async function () {
    [owner, user1, user2] = await ethers.getSigners();

    // 1. Deploy Staking and Reward Tokens
    const StakingToken = await ethers.getContractFactory("StakingToken");
    stakingToken = await StakingToken.deploy();
    await stakingToken.waitForDeployment();

    const RewardToken = await ethers.getContractFactory("RewardToken");
    rewardToken = await RewardToken.deploy();
    await rewardToken.waitForDeployment();

    // 2. Deploy MockPermit2 and inject bytecode at canonical Permit2 address
    const MockPermit2 = await ethers.getContractFactory("MockPermit2");
    const mockPermit2 = await MockPermit2.deploy();
    await mockPermit2.waitForDeployment();
    
    const bytecode = await ethers.provider.getCode(mockPermit2.target);
    await ethers.provider.send("hardhat_setCode", [PERMIT2_ADDRESS, bytecode]);

    // 3. Deploy StakingRewards
    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    stakingRewards = await StakingRewards.deploy(stakingToken.target, rewardToken.target);
    await stakingRewards.waitForDeployment();

    // 4. Deploy AMMPool (StakingToken = tokenA, RewardToken = tokenB)
    const AMMPool = await ethers.getContractFactory("AMMPool");
    ammPool = await AMMPool.deploy(stakingToken.target, rewardToken.target);
    await ammPool.waitForDeployment();

    // 5. Deploy LendingPool and PriceFeed
    const MockPriceFeed = await ethers.getContractFactory("MockPriceFeed");
    priceFeed = await MockPriceFeed.deploy();
    await priceFeed.waitForDeployment();

    const LendingPool = await ethers.getContractFactory("LendingPool");
    lendingPool = await LendingPool.deploy(priceFeed.target, stakingToken.target, rewardToken.target);
    await lendingPool.waitForDeployment();

    // Mint tokens to users and contracts
    await stakingToken.mint(user1.address, ethers.parseEther("10000"));
    await rewardToken.mint(user1.address, ethers.parseEther("10000"));
    await stakingToken.mint(owner.address, ethers.parseEther("10000"));
    await rewardToken.mint(owner.address, ethers.parseEther("10000"));
    await rewardToken.mint(stakingRewards.target, ethers.parseEther("50000"));
    await rewardToken.mint(lendingPool.target, ethers.parseEther("50000"));

    // Configure PriceFeed prices: STK = $2, RWD = $1
    await priceFeed.setPrice(stakingToken.target, ethers.parseEther("2"));
    await priceFeed.setPrice(rewardToken.target, ethers.parseEther("1"));
  });

  describe("StakingRewards with Permit2", function () {
    it("should allow staking using permit2 signature", async function () {
      const amount = ethers.parseEther("100");
      
      // User must first approve Permit2 to spend their tokens
      await stakingToken.connect(user1).approve(PERMIT2_ADDRESS, amount);

      // Call stakeWithPermit2 with a mock signature
      const nonce = 0;
      const deadline = Math.floor(Date.now() / 1000) + 3600;
      const signature = "0x1234567890abcdef";

      await stakingRewards.connect(user1).stakeWithPermit2(amount, nonce, deadline, signature);

      const balance = await stakingRewards.balanceOf(user1.address);
      expect(balance).to.equal(amount);
    });

    it("should fallback to standard approve/transferFrom when signature is empty", async function () {
      const amount = ethers.parseEther("50");
      const currentStaked = await stakingRewards.balanceOf(user1.address);

      // Standard approve to StakingRewards contract
      await stakingToken.connect(user1).approve(stakingRewards.target, amount);

      // Call stakeWithPermit2 with empty signature (fallback route)
      await stakingRewards.connect(user1).stakeWithPermit2(amount, 0, 0, "0x");

      const balance = await stakingRewards.balanceOf(user1.address);
      expect(balance).to.equal(currentStaked + amount);
    });
  });

  describe("AMMPool with Permit2", function () {
    before(async function () {
      // Add initial liquidity to AMMPool
      const amtA = ethers.parseEther("1000");
      const amtB = ethers.parseEther("1000");
      await stakingToken.connect(owner).approve(ammPool.target, amtA);
      await rewardToken.connect(owner).approve(ammPool.target, amtB);
      await ammPool.connect(owner).addLiquidity(amtA, amtB);
    });

    it("should allow swapping using permit2 signature", async function () {
      const amountIn = ethers.parseEther("10");
      const minAmountOut = ethers.parseEther("9");

      // Approve Permit2
      await stakingToken.connect(user1).approve(PERMIT2_ADDRESS, amountIn);

      const nonce = 1;
      const deadline = Math.floor(Date.now() / 1000) + 3600;
      const signature = "0x1234567890abcdef";

      const balanceBefore = await rewardToken.balanceOf(user1.address);

      await ammPool.connect(user1).swapWithPermit2(
        stakingToken.target,
        amountIn,
        minAmountOut,
        nonce,
        deadline,
        signature
      );

      const balanceAfter = await rewardToken.balanceOf(user1.address);
      expect(balanceAfter).to.be.gt(balanceBefore);
    });

    it("should fallback to standard swap when signature is empty", async function () {
      const amountIn = ethers.parseEther("10");
      const minAmountOut = ethers.parseEther("9");

      // Standard approve to AMMPool
      await stakingToken.connect(user1).approve(ammPool.target, amountIn);

      const balanceBefore = await rewardToken.balanceOf(user1.address);

      await ammPool.connect(user1).swapWithPermit2(
        stakingToken.target,
        amountIn,
        minAmountOut,
        0,
        0,
        "0x"
      );

      const balanceAfter = await rewardToken.balanceOf(user1.address);
      expect(balanceAfter).to.be.gt(balanceBefore);
    });
  });

  describe("LendingPool with Permit2", function () {
    it("should allow deposit and repay via permit2 signature", async function () {
      const depositAmount = ethers.parseEther("100");
      const borrowAmount = ethers.parseEther("50");

      // Approve Permit2 for deposit
      await stakingToken.connect(user1).approve(PERMIT2_ADDRESS, depositAmount);

      const nonce = 2;
      const deadline = Math.floor(Date.now() / 1000) + 3600;
      const signature = "0x1234567890abcdef";

      // 1. Deposit with Permit2 signature
      await lendingPool.connect(user1).depositWithPermit2(depositAmount, nonce, deadline, signature);

      let pos = await lendingPool.getPosition(user1.address);
      expect(pos.collateral).to.equal(depositAmount);

      // Borrow
      await lendingPool.connect(user1).borrow(borrowAmount);
      pos = await lendingPool.getPosition(user1.address);
      expect(pos.debt).to.equal(borrowAmount);

      // Approve Permit2 for repay
      await rewardToken.connect(user1).approve(PERMIT2_ADDRESS, borrowAmount);

      // 2. Repay with Permit2 signature
      await lendingPool.connect(user1).repayWithPermit2(borrowAmount, nonce + 1, deadline, signature);
      pos = await lendingPool.getPosition(user1.address);
      expect(pos.debt).to.equal(0n);
    });

    it("should fallback to standard deposit and repay when signature is empty", async function () {
      const depositAmount = ethers.parseEther("50");
      const borrowAmount = ethers.parseEther("20");

      const posBefore = await lendingPool.getPosition(user1.address);

      // Standard approve to LendingPool
      await stakingToken.connect(user1).approve(lendingPool.target, depositAmount);

      // 1. Fallback Deposit
      await lendingPool.connect(user1).depositWithPermit2(depositAmount, 0, 0, "0x");

      let pos = await lendingPool.getPosition(user1.address);
      expect(pos.collateral).to.equal(posBefore.collateral + depositAmount);

      // Borrow
      await lendingPool.connect(user1).borrow(borrowAmount);

      // Standard approve borrowToken
      await rewardToken.connect(user1).approve(lendingPool.target, borrowAmount);

      // 2. Fallback Repay
      await lendingPool.connect(user1).repayWithPermit2(borrowAmount, 0, 0, "0x");

      pos = await lendingPool.getPosition(user1.address);
      expect(pos.debt).to.equal(0n);
    });
  });
});
