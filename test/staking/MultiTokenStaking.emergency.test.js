const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MultiTokenStaking - EmergencyWithdraw", function () {
    let staking, rewardToken, stakeToken, owner, user;

    beforeEach(async function () {
        [owner, user] = await ethers.getSigners();

        const MockToken = await ethers.getContractFactory("MockERC20");
        rewardToken = await MockToken.deploy("Reward", "RWD", 18);
        stakeToken = await MockToken.deploy("Stake", "STK", 18);

        const MultiTokenStaking = await ethers.getContractFactory("MultiTokenStaking");
        staking = await MultiTokenStaking.deploy(rewardToken.address, ethers.parseEther("1"));

        await staking.addPool(100, stakeToken.address);

        await stakeToken.mint(user.address, ethers.parseEther("1000"));
        await stakeToken.connect(user).approve(staking.address, ethers.MaxUint256);
    });

    it("should allow emergency withdraw without rewards", async function () {
        await staking.connect(user).deposit(0, ethers.parseEther("100"));
        
        const userInfoBefore = await staking.userInfo(0, user.address);
        expect(userInfoBefore.amount).to.equal(ethers.parseEther("100"));

        await staking.connect(user).emergencyWithdraw(0);

        const balance = await stakeToken.balanceOf(user.address);
        expect(balance).to.equal(ethers.parseEther("1000"));

        const userInfoAfter = await staking.userInfo(0, user.address);
        expect(userInfoAfter.amount).to.equal(0);
        expect(userInfoAfter.rewardDebt).to.equal(0);

        const poolInfo = await staking.poolInfo(0);
        expect(poolInfo.totalStaked).to.equal(0);
    });

    it("should emit EmergencyWithdraw event", async function () {
        await staking.connect(user).deposit(0, ethers.parseEther("50"));

        await expect(staking.connect(user).emergencyWithdraw(0))
            .to.emit(staking, "EmergencyWithdraw")
            .withArgs(user.address, 0, ethers.parseEther("50"));
    });

    it("should revert if nothing to withdraw", async function () {
        await expect(staking.connect(user).emergencyWithdraw(0))
            .to.be.revertedWith("MultiStaking: nothing to withdraw");
    });
});
