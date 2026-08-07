const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PrizeSplit Dust Test", function () {
    let PrizeSplit, prizeSplit, winner1, winner2, owner;

    beforeEach(async function () {
        [owner, winner1, winner2] = await ethers.getSigners();
        PrizeSplit = await ethers.getContractFactory("PrizeSplit");
        prizeSplit = await PrizeSplit.deploy();
        await prizeSplit.deployed();

        await owner.sendTransaction({ to: prizeSplit.address, value: ethers.utils.parseEther("1.001") });
    });

    it("allocates dust to last winner", async function () {
        const initialBalanceWinner1 = await ethers.provider.getBalance(winner1.address);
        const initialBalanceWinner2 = await ethers.provider.getBalance(winner2.address);

        await prizeSplit.claimPrize([winner1.address, winner2.address], [ethers.utils.parseEther("0.5"), ethers.utils.parseEther("0.5")]);

        const finalBalanceWinner1 = await ethers.provider.getBalance(winner1.address);
        const finalBalanceWinner2 = await ethers.provider.getBalance(winner2.address);

        expect(finalBalanceWinner2.sub(initialBalanceWinner2)).to.equal(ethers.utils.parseEther("0.501"));
    });
});
