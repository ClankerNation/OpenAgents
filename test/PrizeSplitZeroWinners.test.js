const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PrizeSplit Zero Winners Test", function () {
    let PrizeSplit, prizeSplit, owner;

    beforeEach(async function () {
        [owner] = await ethers.getSigners();
        PrizeSplit = await ethers.getContractFactory("PrizeSplit");
        prizeSplit = await PrizeSplit.deploy();
        await prizeSplit.deployed();

        await owner.sendTransaction({ to: prizeSplit.address, value: ethers.utils.parseEther("1.0") });
    });

    it("reverts when no winners", async function () {
        await expect(prizeSplit.claimPrize([], [])).to.be.revertedWith("No winners");
    });
});
