const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("GovernorAlpha quorum execute checks", function () {
  let token;
  let governor;
  let admin;
  let proposer;
  let smallVoter;
  let quorumVoter;
  let outsider;

  const parse = ethers.parseEther;

  async function mineBlocks(count) {
    if (count <= 0) return;
    await ethers.provider.send("hardhat_mine", [`0x${count.toString(16)}`]);
  }

  async function createEmptyProposal() {
    await governor.connect(proposer).propose([], [], []);
    return await governor.proposalCount();
  }

  async function moveToExecutionWindow(proposalId) {
    const proposal = await governor.proposals(proposalId);
    const endBlock = Number(proposal.endBlock);
    const currentBlock = await ethers.provider.getBlockNumber();
    await mineBlocks(endBlock - currentBlock + 1);
  }

  beforeEach(async function () {
    [admin, proposer, smallVoter, quorumVoter, outsider] = await ethers.getSigners();

    const MockVotesToken = await ethers.getContractFactory("MockERC20Votes");
    token = await MockVotesToken.deploy();
    await token.waitForDeployment();

    const GovernorAlpha = await ethers.getContractFactory("GovernorAlpha");
    governor = await GovernorAlpha.deploy(await token.getAddress());
    await governor.waitForDeployment();

    await token.mint(await proposer.getAddress(), parse("100000"));
    await token.mint(await smallVoter.getAddress(), parse("1"));
    await token.mint(await quorumVoter.getAddress(), parse("40000"));

    await token.connect(proposer).delegate(await proposer.getAddress());
    await token.connect(smallVoter).delegate(await smallVoter.getAddress());
    await token.connect(quorumVoter).delegate(await quorumVoter.getAddress());
  });

  it("reverts execution when forVotes is below quorum", async function () {
    const proposalId = await createEmptyProposal();

    await mineBlocks(1);
    await governor.connect(smallVoter).vote(proposalId, true);
    await moveToExecutionWindow(proposalId);

    await expect(governor.execute(proposalId)).to.be.revertedWith("Governor: quorum not reached");
  });

  it("executes normally when forVotes is at quorum with majority", async function () {
    const proposalId = await createEmptyProposal();

    await mineBlocks(1);
    await governor.connect(quorumVoter).vote(proposalId, true);
    await moveToExecutionWindow(proposalId);

    await expect(governor.execute(proposalId)).to.emit(governor, "ProposalExecuted").withArgs(proposalId);

    const proposal = await governor.proposals(proposalId);
    expect(proposal.executed).to.equal(true);
  });

  it("allows admin to update quorum and blocks non-admin", async function () {
    await expect(
      governor.connect(outsider).setQuorumVotes(parse("50000"))
    ).to.be.revertedWith("Governor: not admin");

    await expect(governor.connect(admin).setQuorumVotes(parse("50000")))
      .to.emit(governor, "QuorumVotesUpdated")
      .withArgs(parse("40000"), parse("50000"));

    expect(await governor.quorumVotes()).to.equal(parse("50000"));
  });
});
