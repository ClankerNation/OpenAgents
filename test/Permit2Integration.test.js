const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Permit2 Integration Tests", function () {
  let owner, user, staker, liquidator;
  let stakingToken, rewardToken;
  let stakingRewards, ammPool, lendingPool, priceFeed;
  let permit2;
  const permit2Address = "0x000000000022D473030F116dDEE9F6B43aC78BA3";

  beforeEach(async function () {
    [owner, user, staker, liquidator] = await ethers.getSigners();

    // 1. Deploy StakingToken & RewardToken
    const ERC20Factory = await ethers.getContractFactory("StakingToken");
    stakingToken = await ERC20Factory.deploy();
    await stakingToken.waitForDeployment();

    const RewardTokenFactory = await ethers.getContractFactory("RewardToken");
    rewardToken = await RewardTokenFactory.deploy();
    await rewardToken.waitForDeployment();

    // 2. Deploy MockPermit2 & override canonical address
    const MockPermit2 = await ethers.getContractFactory("MockPermit2");
    const mockPermit2 = await MockPermit2.deploy();
    await mockPermit2.waitForDeployment();

    const bytecode = await ethers.provider.getCode(mockPermit2.target);
    await ethers.provider.send("hardhat_setCode", [permit2Address, bytecode]);

    permit2 = await ethers.getContractAt("MockPermit2", permit2Address);

    // 3. Deploy StakingRewards
    const StakingRewards = await ethers.getContractFactory("StakingRewards");
    stakingRewards = await StakingRewards.deploy(stakingToken.target, rewardToken.target);
    await stakingRewards.waitForDeployment();

    // 4. Deploy AMMPool
    const AMMPool = await ethers.getContractFactory("AMMPool");
    ammPool = await AMMPool.deploy(stakingToken.target, rewardToken.target);
    await ammPool.waitForDeployment();

    // 5. Deploy LendingPool with MockPriceFeed
    const MockPriceFeed = await ethers.getContractFactory("MockPriceFeed");
    priceFeed = await MockPriceFeed.deploy();
    await priceFeed.waitForDeployment();

    // Set prices: stakingToken = $10, rewardToken = $2
    await priceFeed.setPrice(stakingToken.target, ethers.parseEther("10"));
    await priceFeed.setPrice(rewardToken.target, ethers.parseEther("2"));

    const LendingPool = await ethers.getContractFactory("LendingPool");
    lendingPool = await LendingPool.deploy(priceFeed.target, stakingToken.target, rewardToken.target);
    await lendingPool.waitForDeployment();

    // Setup initial balances
    await stakingToken.mint(user.address, ethers.parseEther("10000"));
    await rewardToken.mint(user.address, ethers.parseEther("10000"));

    await stakingToken.mint(staker.address, ethers.parseEther("10000"));
    await rewardToken.mint(staker.address, ethers.parseEther("10000"));

    // Set approvals for Permit2 on the tokens (for the permit2 test user)
    await stakingToken.connect(user).approve(permit2Address, ethers.MaxUint256);
    await rewardToken.connect(user).approve(permit2Address, ethers.MaxUint256);

    await stakingToken.connect(staker).approve(permit2Address, ethers.MaxUint256);
    await rewardToken.connect(staker).approve(permit2Address, ethers.MaxUint256);
  });

  async function getPermitSignature(signer, tokenAddress, amount, spender, nonce, deadline) {
    const chainId = (await ethers.provider.getNetwork()).chainId;

    const domain = {
      name: "Permit2",
      chainId: chainId,
      verifyingContract: permit2Address
    };

    const types = {
      PermitTransferFrom: [
        { name: "permitted", type: "TokenPermissions" },
        { name: "spender", type: "address" },
        { name: "nonce", type: "uint256" },
        { name: "deadline", type: "uint256" }
      ],
      TokenPermissions: [
        { name: "token", type: "address" },
        { name: "amount", type: "uint256" }
      ]
    };

    const value = {
      permitted: {
        token: tokenAddress,
        amount: amount
      },
      spender: spender,
      nonce: nonce,
      deadline: deadline
    };

    return await signer.signTypedData(domain, types, value);
  }

  describe("StakingRewards Permit2 Integration", function () {
    it("should allow staking using Permit2 signature", async function () {
      const stakeAmount = ethers.parseEther("100");
      const nonce = 0;
      const deadline = Math.floor(Date.now() / 1000) + 3600;

      const signature = await getPermitSignature(
        user,
        stakingToken.target,
        stakeAmount,
        stakingRewards.target,
        nonce,
        deadline
      );

      await expect(
        stakingRewards.connect(user).stakeWithPermit(stakeAmount, nonce, deadline, signature)
      ).to.emit(stakingRewards, "Staked").withArgs(user.address, stakeAmount);

      expect(await stakingRewards.balanceOf(user.address)).to.equal(stakeAmount);
    });

    it("should fallback to standard approve/transferFrom flow", async function () {
      const stakeAmount = ethers.parseEther("50");
      await stakingToken.connect(user).approve(stakingRewards.target, stakeAmount);

      await expect(
        stakingRewards.connect(user).stake(stakeAmount)
      ).to.emit(stakingRewards, "Staked").withArgs(user.address, stakeAmount);

      expect(await stakingRewards.balanceOf(user.address)).to.equal(stakeAmount);
    });
  });

  describe("AMMPool Permit2 Integration", function () {
    beforeEach(async function () {
      // Add initial liquidity to AMM Pool
      const liquidityA = ethers.parseEther("1000");
      const liquidityB = ethers.parseEther("2000");
      await stakingToken.connect(user).approve(ammPool.target, liquidityA);
      await rewardToken.connect(user).approve(ammPool.target, liquidityB);
      await ammPool.connect(user).addLiquidity(liquidityA, liquidityB);
    });

    it("should allow swap using Permit2 signature", async function () {
      const swapAmount = ethers.parseEther("10");
      const minAmountOut = 0;
      const nonce = 0;
      const deadline = Math.floor(Date.now() / 1000) + 3600;

      const signature = await getPermitSignature(
        staker,
        stakingToken.target,
        swapAmount,
        ammPool.target,
        nonce,
        deadline
      );

      const balanceBefore = await rewardToken.balanceOf(staker.address);

      await expect(
        ammPool.connect(staker).swapWithPermit(
          stakingToken.target,
          swapAmount,
          minAmountOut,
          nonce,
          deadline,
          signature
        )
      ).to.emit(ammPool, "Swap");

      const balanceAfter = await rewardToken.balanceOf(staker.address);
      expect(balanceAfter).to.be.gt(balanceBefore);
    });

    it("should fallback to standard swap flow", async function () {
      const swapAmount = ethers.parseEther("10");
      const minAmountOut = 0;

      await stakingToken.connect(staker).approve(ammPool.target, swapAmount);

      const balanceBefore = await rewardToken.balanceOf(staker.address);

      await expect(
        ammPool.connect(staker).swap(stakingToken.target, swapAmount, minAmountOut)
      ).to.emit(ammPool, "Swap");

      const balanceAfter = await rewardToken.balanceOf(staker.address);
      expect(balanceAfter).to.be.gt(balanceBefore);
    });
  });

  describe("LendingPool Permit2 Integration", function () {
    it("should allow deposit using Permit2 signature", async function () {
      const depositAmount = ethers.parseEther("100");
      const nonce = 0;
      const deadline = Math.floor(Date.now() / 1000) + 3600;

      const signature = await getPermitSignature(
        user,
        stakingToken.target,
        depositAmount,
        lendingPool.target,
        nonce,
        deadline
      );

      await expect(
        lendingPool.connect(user).depositWithPermit(depositAmount, nonce, deadline, signature)
      ).to.emit(lendingPool, "Deposited").withArgs(user.address, depositAmount);

      const pos = await lendingPool.getPosition(user.address);
      expect(pos.collateral).to.equal(depositAmount);
    });

    it("should fallback to standard deposit flow", async function () {
      const depositAmount = ethers.parseEther("50");
      await stakingToken.connect(user).approve(lendingPool.target, depositAmount);

      await expect(
        lendingPool.connect(user).deposit(depositAmount)
      ).to.emit(lendingPool, "Deposited").withArgs(user.address, depositAmount);

      const pos = await lendingPool.getPosition(user.address);
      expect(pos.collateral).to.equal(depositAmount);
    });
  });
});
