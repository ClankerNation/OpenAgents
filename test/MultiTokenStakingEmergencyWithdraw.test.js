const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MultiTokenStaking emergencyWithdraw", function () {
  async function deployFixture() {
    const [, staker] = await ethers.getSigners();
    const amount = ethers.parseEther("100");

    const AgentToken = await ethers.getContractFactory("AgentToken");
    const stakeToken = await AgentToken.deploy("Stake Token", "STK", 0);
    await stakeToken.waitForDeployment();
    const rewardToken = await AgentToken.deploy("Reward Token", "RWD", 0);
    await rewardToken.waitForDeployment();

    const MultiTokenStaking = await ethers.getContractFactory("MultiTokenStaking");
    const staking = await MultiTokenStaking.deploy(await rewardToken.getAddress(), ethers.parseEther("1"));
    await staking.waitForDeployment();

    await staking.addPool(100, await stakeToken.getAddress());
    await stakeToken.mint(staker.address, amount);
    await rewardToken.mint(await staking.getAddress(), ethers.parseEther("1000"));
    await stakeToken.connect(staker).approve(await staking.getAddress(), amount);
    await staking.connect(staker).deposit(0, amount);

    return { amount, rewardToken, stakeToken, staker, staking };
  }

  it("returns staked tokens without rewards and resets accounting", async function () {
    const { amount, rewardToken, stakeToken, staker, staking } = await deployFixture();

    await ethers.provider.send("evm_increaseTime", [3600]);
    await ethers.provider.send("evm_mine");

    await expect(staking.connect(staker).emergencyWithdraw(0))
      .to.emit(staking, "EmergencyWithdraw")
      .withArgs(staker.address, 0, amount);

    expect(await stakeToken.balanceOf(staker.address)).to.equal(amount);
    expect(await rewardToken.balanceOf(staker.address)).to.equal(0);

    const user = await staking.userInfo(0, staker.address);
    expect(user.amount).to.equal(0);
    expect(user.rewardDebt).to.equal(0);

    const pool = await staking.poolInfo(0);
    expect(pool.totalStaked).to.equal(0);
  });

  it("reverts when the caller has no stake in the pool", async function () {
    const { staker, staking } = await deployFixture();
    await staking.connect(staker).emergencyWithdraw(0);

    await expect(staking.connect(staker).emergencyWithdraw(0)).to.be.revertedWith(
      "MultiStaking: nothing to withdraw"
    );
  });
});
