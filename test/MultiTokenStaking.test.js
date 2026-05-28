const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MultiTokenStaking", function () {
  let staking, stakeToken, rewardToken;
  let owner, user1;

  beforeEach(async function () {
    [owner, user1] = await ethers.getSigners();

    const StakeToken = await ethers.getContractFactory("StakingToken");
    stakeToken = await StakeToken.deploy();
    await stakeToken.deployed();

    const RewardToken = await ethers.getContractFactory("StakingToken");
    rewardToken = await RewardToken.deploy();
    await rewardToken.deployed();

    const Staking = await ethers.getContractFactory("MultiTokenStaking");
    staking = await Staking.deploy(rewardToken.address, ethers.utils.parseEther("1"));
    await staking.deployed();

    await staking.addPool(100, stakeToken.address);

    await stakeToken.mint(user1.address, ethers.utils.parseEther("1000"));
    await rewardToken.mint(staking.address, ethers.utils.parseEther("10000"));
  });

  describe("emergencyWithdraw", function () {
    it("should return staked tokens without rewards", async function () {
      const amount = ethers.utils.parseEther("100");
      await stakeToken.connect(user1).approve(staking.address, amount);
      await staking.connect(user1).deposit(0, amount);

      const balanceBefore = await stakeToken.balanceOf(user1.address);
      await staking.connect(user1).emergencyWithdraw(0);
      const balanceAfter = await stakeToken.balanceOf(user1.address);

      expect(balanceAfter.sub(balanceBefore)).to.equal(amount);
    });

    it("should reset user amount to zero", async function () {
      const amount = ethers.utils.parseEther("100");
      await stakeToken.connect(user1).approve(staking.address, amount);
      await staking.connect(user1).deposit(0, amount);

      await staking.connect(user1).emergencyWithdraw(0);

      const userInfo = await staking.userInfo(0, user1.address);
      expect(userInfo.amount).to.equal(0);
    });

    it("should reset reward debt to zero", async function () {
      const amount = ethers.utils.parseEther("100");
      await stakeToken.connect(user1).approve(staking.address, amount);
      await staking.connect(user1).deposit(0, amount);

      await staking.connect(user1).emergencyWithdraw(0);

      const userInfo = await staking.userInfo(0, user1.address);
      expect(userInfo.rewardDebt).to.equal(0);
    });

    it("should update pool total staked", async function () {
      const amount = ethers.utils.parseEther("100");
      await stakeToken.connect(user1).approve(staking.address, amount);
      await staking.connect(user1).deposit(0, amount);

      await staking.connect(user1).emergencyWithdraw(0);

      const pool = await staking.poolInfo(0);
      expect(pool.totalStaked).to.equal(0);
    });

    it("should emit EmergencyWithdraw event", async function () {
      const amount = ethers.utils.parseEther("100");
      await stakeToken.connect(user1).approve(staking.address, amount);
      await staking.connect(user1).deposit(0, amount);

      await expect(staking.connect(user1).emergencyWithdraw(0))
        .to.emit(staking, "EmergencyWithdraw")
        .withArgs(user1.address, 0, amount);
    });

    it("should reject if no balance", async function () {
      await expect(
        staking.connect(user1).emergencyWithdraw(0)
      ).to.be.revertedWith("MultiStaking: no balance");
    });
  });
});
