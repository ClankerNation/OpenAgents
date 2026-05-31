const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MultiTokenStaking emergencyWithdraw", function () {
  let owner;
  let staker;
  let rewardToken;
  let stakeToken;
  let staking;

  beforeEach(async function () {
    [owner, staker] = await ethers.getSigners();

    const AgentToken = await ethers.getContractFactory("AgentToken");
    rewardToken = await AgentToken.deploy("Reward Token", "RWD", 0);
    await rewardToken.waitForDeployment();

    stakeToken = await AgentToken.deploy("Stake Token", "STK", 0);
    await stakeToken.waitForDeployment();

    const MultiTokenStaking = await ethers.getContractFactory("MultiTokenStaking");
    staking = await MultiTokenStaking.deploy(await rewardToken.getAddress(), ethers.parseEther("1"));
    await staking.waitForDeployment();

    await staking.addPool(100, await stakeToken.getAddress());
    await rewardToken.mint(await staking.getAddress(), ethers.parseEther("100000"));
    await stakeToken.mint(staker.address, ethers.parseEther("100"));
  });

  it("allows emergency withdraw with no rewards and updates pool/user accounting", async function () {
    const amount = ethers.parseEther("100");

    await stakeToken.connect(staker).approve(await staking.getAddress(), amount);
    await staking.connect(staker).deposit(0, amount);

    await ethers.provider.send("evm_increaseTime", [3600]);
    await ethers.provider.send("evm_mine", []);

    const rewardBefore = await rewardToken.balanceOf(staker.address);
    await expect(staking.connect(staker).emergencyWithdraw(0))
      .to.emit(staking, "EmergencyWithdraw")
      .withArgs(staker.address, 0, amount);

    const rewardAfter = await rewardToken.balanceOf(staker.address);
    expect(rewardAfter).to.equal(rewardBefore);

    const user = await staking.userInfo(0, staker.address);
    expect(user.amount).to.equal(0n);
    expect(user.rewardDebt).to.equal(0n);

    const pool = await staking.poolInfo(0);
    expect(pool.totalStaked).to.equal(0n);
    expect(await stakeToken.balanceOf(staker.address)).to.equal(amount);
  });

  it("reverts emergency withdraw when user has no staked amount", async function () {
    await expect(staking.connect(staker).emergencyWithdraw(0)).to.be.revertedWith(
      "MultiStaking: no staked amount"
    );
  });
});
