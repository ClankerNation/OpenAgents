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
    await expect(governorAlpha.execute(proposalId)).to.be.revertedWith(
      "GovernorAlpha::execute: quorum not reached"
    );
  });

  it("Should execute if forVotes meets quorum and has majority", async function () {
    // Setup a proposal with enough votes to meet quorum and has majority
    const proposalId = 1; // Assuming proposalId is 1 for simplicity
    // Simulate voting logic to meet quorum and have majority
    await governorAlpha.setQuorumVotes(1); // Set quorum to 1 for testing purposes
    await governorAlpha.vote(proposalId, true); // Vote FOR the proposal
    await governorAlpha.vote(proposalId, false); // Vote AGAINST the proposal
    await expect(governorAlpha.execute(proposalId)).not.to.be.reverted;
  });

  it("Should allow admin to update QUORUM_VOTES", async function () {
    const newQuorumVotes = 5;
    await governorAlpha.setQuorumVotes(newQuorumVotes);
    expect(await governorAlpha.quorumVotes()).to.equal(newQuorumVotes);
  });
});
