const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Permit2 Integrations", function () {
  let stakingToken, tokenB;
  let stakingRewards, ammPool, lendingPool;
  let owner, user;
  const PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3";

  before(async function () {
    [owner, user] = await ethers.getSigners();

    // 1. Deploy MockPermit2 and inject bytecode into the canonical Permit2 address
    const MockPermit2 = await ethers.getContractFactory("MockPermit2");
    const mockPermit2 = await MockPermit2.deploy();
    await mockPermit2.waitForDeployment();

    const permit2Bytecode = await ethers.provider.getCode(mockPermit2.target);
    await ethers.provider.send("hardhat_setCode", [
      PERMIT2_ADDRESS,
      permit2Bytecode,
    ]);

    // 2. Deploy tokens
    const StakingToken = await ethers.getContractFactory("StakingToken");
    stakingToken = await StakingToken.deploy();
    await stakingToken.waitForDeployment();

    const RewardToken = await ethers.getContractFactory("RewardToken");
    tokenB = await RewardToken.deploy();
    await tokenB.waitForDeployment();

    // Mint tokens to user
    await stakingToken.mint(user.address, ethers.parseEther("1000"));
    await tokenB.mint(user.address, ethers.parseEther("1000"));

    // 3. Deploy StakingRewards
    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    stakingRewards = await StakingRewards.deploy(stakingToken.target, tokenB.target);
    await stakingRewards.waitForDeployment();

    // 4. Deploy AMMPool
    const AMMPool = await ethers.getContractFactory("AMMPool");
    ammPool = await AMMPool.deploy(stakingToken.target, tokenB.target);
    await ammPool.waitForDeployment();

    // Add some initial liquidity to AMMPool
    await stakingToken.mint(owner.address, ethers.parseEther("1000"));
    await tokenB.mint(owner.address, ethers.parseEther("1000"));
    await stakingToken.connect(owner).approve(ammPool.target, ethers.parseEther("1000"));
    await tokenB.connect(owner).approve(ammPool.target, ethers.parseEther("1000"));
    await ammPool.connect(owner).addLiquidity(ethers.parseEther("1000"), ethers.parseEther("1000"));

    // 5. Deploy LendingPool (with a dummy oracle address)
    const LendingPool = await ethers.getContractFactory("LendingPool");
    lendingPool = await LendingPool.deploy(owner.address, stakingToken.target, tokenB.target);
    await lendingPool.waitForDeployment();
  });

  describe("StakingRewards Permit2", function () {
    it("should allow standard stake with fallback approve", async function () {
      const amount = ethers.parseEther("10");
      await stakingToken.connect(user).approve(stakingRewards.target, amount);
      await stakingRewards.connect(user).stake(amount);

      const balance = await stakingRewards.balanceOf(user.address);
      expect(balance).to.equal(amount);
    });

    it("should allow stakeWithPermit using Permit2 signature transfer", async function () {
      const amount = ethers.parseEther("20");
      const nonce = 0;
      const deadline = Math.floor(Date.now() / 1000) + 3600;
      const dummySignature = "0x";

      // User must approve Permit2 canonical address to transfer their tokens
      await stakingToken.connect(user).approve(PERMIT2_ADDRESS, amount);

      // Now stake using permit2
      const initialBalance = await stakingRewards.balanceOf(user.address);
      await stakingRewards.connect(user).stakeWithPermit(amount, nonce, deadline, dummySignature);

      const finalBalance = await stakingRewards.balanceOf(user.address);
      expect(finalBalance - initialBalance).to.equal(amount);
    });
  });

  describe("AMMPool Permit2", function () {
    it("should allow swapWithPermit using Permit2 signature transfer", async function () {
      const amountIn = ethers.parseEther("10");
      const minAmountOut = 0; // slip tolerance
      const nonce = 0;
      const deadline = Math.floor(Date.now() / 1000) + 3600;
      const dummySignature = "0x";

      // User must approve Permit2
      await stakingToken.connect(user).approve(PERMIT2_ADDRESS, amountIn);

      const userInitialTokenB = await tokenB.balanceOf(user.address);
      await ammPool.connect(user).swapWithPermit(
        stakingToken.target,
        amountIn,
        minAmountOut,
        nonce,
        deadline,
        dummySignature
      );

      const userFinalTokenB = await tokenB.balanceOf(user.address);
      expect(userFinalTokenB).to.be.gt(userInitialTokenB);
    });
  });

  describe("LendingPool Permit2", function () {
    it("should allow depositWithPermit using Permit2 signature transfer", async function () {
      const amount = ethers.parseEther("15");
      const nonce = 0;
      const deadline = Math.floor(Date.now() / 1000) + 3600;
      const dummySignature = "0x";

      // User must approve Permit2
      await stakingToken.connect(user).approve(PERMIT2_ADDRESS, amount);

      const initialPos = await lendingPool.getPosition(user.address);
      await lendingPool.connect(user).depositWithPermit(
        amount,
        nonce,
        deadline,
        dummySignature
      );

      const finalPos = await lendingPool.getPosition(user.address);
      expect(finalPos.collateral - initialPos.collateral).to.equal(amount);
    });
  });
});
