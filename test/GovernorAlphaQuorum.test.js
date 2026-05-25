const { expect } = require("chai");
const { ethers } = require("hardhat");

async function mineBlocks(count) {
  await ethers.provider.send("hardhat_mine", [ethers.toQuantity(count)]);
}

describe("GovernorAlpha quorum", function () {
  let admin;
  let proposer;
  let treasury;
  let outsider;
  let token;
  let governor;
  let target;

  const proposerVotes = ethers.parseEther("150000");
  const treasuryVotes = ethers.parseEther("9850000");
  const loweredQuorum = proposerVotes;

  beforeEach(async function () {
    [admin, proposer, treasury, outsider] = await ethers.getSigners();

    const MockVotesToken = await ethers.getContractFactory("MockVotesToken");
    token = await MockVotesToken.deploy();
    await token.waitForDeployment();

    await token.mint(proposer.address, proposerVotes);
    await token.mint(treasury.address, treasuryVotes);
    await token.connect(proposer).delegate(proposer.address);
    await mineBlocks(1);

    const GovernorAlpha = await ethers.getContractFactory("GovernorAlpha");
    governor = await GovernorAlpha.deploy(await token.getAddress());
    await governor.waitForDeployment();

    const MockGovernorTarget = await ethers.getContractFactory("MockGovernorTarget");
    target = await MockGovernorTarget.deploy();
    await target.waitForDeployment();
  });

  async function createProposal(value) {
    const calldata = target.interface.encodeFunctionData("setValue", [value]);
    await governor.connect(proposer).propose([await target.getAddress()], [0], [calldata]);
    return 1n;
  }

  async function voteForAndFinish(proposalId) {
    await mineBlocks(2);
    await governor.connect(proposer).vote(proposalId, true);
    await mineBlocks(17282);
  }

  it("reverts execution when forVotes are below quorum", async function () {
    expect(await governor.QUORUM_VOTES()).to.equal(ethers.parseEther("400000"));
    const proposalId = await createProposal(42);
    await voteForAndFinish(proposalId);

    await expect(governor.execute(proposalId)).to.be.revertedWith("Governor: quorum not reached");
    expect(await target.value()).to.equal(0n);
  });

  it("executes a majority proposal when forVotes meet quorum exactly", async function () {
    const originalQuorum = await governor.QUORUM_VOTES();

    await expect(governor.setQuorumVotes(loweredQuorum))
      .to.emit(governor, "QuorumVotesUpdated")
      .withArgs(originalQuorum, loweredQuorum);

    const proposalId = await createProposal(99);
    await voteForAndFinish(proposalId);

    await expect(governor.execute(proposalId))
      .to.emit(governor, "ProposalExecuted")
      .withArgs(proposalId);

    expect(await target.value()).to.equal(99n);
  });

  it("lets only the admin update quorum", async function () {
    await expect(governor.connect(outsider).setQuorumVotes(loweredQuorum)).to.be.revertedWith("Governor: not admin");
    await expect(governor.setQuorumVotes(0)).to.be.revertedWith("Governor: zero quorum");

    await governor.setQuorumVotes(loweredQuorum);
    expect(await governor.QUORUM_VOTES()).to.equal(loweredQuorum);
  });
});
