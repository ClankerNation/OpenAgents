const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MultiTokenStaking - emergencyWithdraw", function () {
  let staking, rewardToken, stakeToken;
  let owner, user;
  const rewardPerSecond = ethers.parseEther("1");

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners();

    const ERC20 = await ethers.getContractFactory("MockERC20");
    rewardToken = await ERC20.deploy("Reward", "RWD", ethers.parseEther("1000000"));
    stakeToken = await ERC20.deploy("Stake", "STK", ethers.parseEther("1000000"));
    await rewardToken.waitForDeployment();
    await stakeToken.waitForDeployment();

    const Staking = await ethers.getContractFactory("MultiTokenStaking");
    staking = await Staking.deploy(await rewardToken.getAddress(), rewardPerSecond);
    await staking.waitForDeployment();

    await staking.addPool(100, await stakeToken.getAddress());
    await stakeToken.transfer(user.address, ethers.parseEther("1000"));
    await stakeToken.connect(user).approve(await staking.getAddress(), ethers.parseEther("1000"));
  });

  it("allows emergency withdraw staked tokens", async function () {
    const amount = ethers.parseEther("100");
    await staking.connect(user).deposit(0, amount);

    const balanceBefore = await stakeToken.balanceOf(user.address);
    await staking.connect(user).emergencyWithdraw(0);
    const balanceAfter = await stakeToken.balanceOf(user.address);

    expect(balanceAfter - balanceBefore).to.equal(amount);
  });

  it("resets user reward debt to zero", async function () {
    const amount = ethers.parseEther("100");
    await staking.connect(user).deposit(0, amount);

    await staking.connect(user).emergencyWithdraw(0);

    const user_info = await staking.userInfo(0, user.address);
    expect(user_info.amount).to.equal(0);
    expect(user_info.rewardDebt).to.equal(0);
  });

  it("decrements pool total staked", async function () {
    const amount = ethers.parseEther("100");
    await staking.connect(user).deposit(0, amount);

    await staking.connect(user).emergencyWithdraw(0);

    const pool = await staking.poolInfo(0);
    expect(pool.totalStaked).to.equal(0);
  });

  it("emits EmergencyWithdraw event", async function () {
    const amount = ethers.parseEther("100");
    await staking.connect(user).deposit(0, amount);

    await expect(staking.connect(user).emergencyWithdraw(0))
      .to.emit(staking, "EmergencyWithdraw")
      .withArgs(user.address, 0, amount);
  });

  it("does not distribute rewards on emergency withdraw", async function () {
    const amount = ethers.parseEther("100");
    await staking.connect(user).deposit(0, amount);

    await ethers.provider.send("evm_increaseTime", [3600]);
    await ethers.provider.send("evm_mine");

    const rewardBefore = await rewardToken.balanceOf(user.address);
    await staking.connect(user).emergencyWithdraw(0);
    const rewardAfter = await rewardToken.balanceOf(user.address);

    expect(rewardAfter).to.equal(rewardBefore);
  });

  it("reverts if nothing staked", async function () {
    await expect(staking.connect(user).emergencyWithdraw(0)).to.be.revertedWith("Nothing staked");
  });
});
