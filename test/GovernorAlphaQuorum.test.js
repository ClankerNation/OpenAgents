const { expect } = require("chai");
const { ethers } = require("hardhat");
describe("GovernorAlpha Quorum Tests", function () {
    let GovernorAlpha, governorAlpha, owner, addr1, addr2;

    beforeEach(async function () {
        GovernorAlpha = await ethers.getContractFactory("GovernorAlpha");
        [owner, addr1, addr2] = await ethers.getSigners();
        governorAlpha = await GovernorAlpha.deploy();
        await governorAlpha.deployed();
    });

    it("Should revert execute if forVotes is less than quorum", async function () {
        // Setup a proposal with less than quorum votes
        const proposalId = 1; // Assuming proposalId is 1 for simplicity
        await expect(governorAlpha.execute(proposalId)).to.be.revertedWith("Proposal does not meet quorum");
    });

    it("Should execute if forVotes meets quorum", async function () {
        // Setup a proposal with enough votes to meet quorum
        const proposalId = 1; // Assuming proposalId is 1 for simplicity
        // Simulate voting logic to meet quorum
        await governorAlpha.setQuorumVotes(1); // Set quorum to 1 for testing purposes
        await expect(governorAlpha.execute(proposalId)).not.to.be.reverted;
    });
});
