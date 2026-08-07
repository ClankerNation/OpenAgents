const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PrizeSplit Reentrancy Test", function () {
    let PrizeSplit, prizeSplit, attacker, owner;

    beforeEach(async function () {
        [owner, attacker] = await ethers.getSigners();
        PrizeSplit = await ethers.getContractFactory("PrizeSplit");
        prizeSplit = await PrizeSplit.deploy();
        await prizeSplit.deployed();

        await owner.sendTransaction({ to: prizeSplit.address, value: ethers.utils.parseEther("1.0") });
    });

    it("reverts on reentrancy", async function () {
        const Attacker = await ethers.getContractFactory("Attacker");
        const attackerContract = await Attacker.deploy(prizeSplit.address);
        await attackerContract.deployed();

        await expect(attackerContract.attack()).to.be.reverted;
    });
});
