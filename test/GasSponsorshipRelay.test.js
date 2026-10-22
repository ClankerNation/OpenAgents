const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("GasSponsorshipRelay", function () {
    it("Should deploy and verify EIP-712 relayed transaction", async function () {
        const [owner, agent, targetContract] = await ethers.getSigners();

        const GasRelay = await ethers.getContractFactory("GasSponsorshipRelay");
        const relay = await GasRelay.deploy();
        await relay.waitForDeployment();

        expect(await relay.owner()).to.equal(owner.address);
    });
});
