const { expect } = require("chai");
const { ethers } = require("hardhat");
const { mine } = require("@nomicfoundation/hardhat-network-helpers");
const fs = require("node:fs");

describe("GovernorAlpha issue #4", function () {
  let governor;
  let token;
  let target;
  let voter;
  let attacker;

  const PROPOSAL_THRESHOLD = ethers.parseEther("100000");

  beforeEach(async function () {
    [, voter, attacker] = await ethers.getSigners();

    const TestToken = await ethers.getContractFactory("GovernorAlphaTestToken");
    token = await TestToken.deploy();
    await token.waitForDeployment();

    const GovernorAlpha = await ethers.getContractFactory("GovernorAlpha");
    governor = await GovernorAlpha.deploy(await token.getAddress());
    await governor.waitForDeployment();

    const Target = await ethers.getContractFactory("GovernorAlphaTarget");
    target = await Target.deploy();
    await target.waitForDeployment();
  });

  async function createProposal() {
    await token.setVotes(voter.address, PROPOSAL_THRESHOLD);

    const calldata = target.interface.encodeFunctionData("setValue", [42]);
    const tx = await governor
      .connect(voter)
      .propose([await target.getAddress()], [0], [calldata]);
    await tx.wait();

    return 1n;
  }

  async function advanceToVotingStart(proposalId) {
    const proposal = await governor.proposals(proposalId);
    const latest = await ethers.provider.getBlockNumber();
    if (latest < Number(proposal.startBlock)) {
      await mine(Number(proposal.startBlock) - latest);
    }
    return proposal;
  }

  it("contains no transaction-origin references in GovernorAlpha.sol", function () {
    const source = fs.readFileSync("contracts/governance/GovernorAlpha.sol", "utf8");
    const vulnerablePattern = ["tx", "origin"].join(".");
    expect(source).not.to.include(vulnerablePattern);
  });

  it("uses msg.sender as the voter identity", async function () {
    const proposalId = await createProposal();
    const proposal = await advanceToVotingStart(proposalId);
    await token.setPastVotes(voter.address, proposal.startBlock, PROPOSAL_THRESHOLD);

    await expect(governor.connect(voter).vote(proposalId, true))
      .to.emit(governor, "VoteCast")
      .withArgs(voter.address, proposalId, true, PROPOSAL_THRESHOLD);
  });

  it("reverts a phishing proxy vote from a voter EOA", async function () {
    const proposalId = await createProposal();
    const proposal = await advanceToVotingStart(proposalId);
    await token.setPastVotes(voter.address, proposal.startBlock, PROPOSAL_THRESHOLD);

    const PhishingProxy = await ethers.getContractFactory("GovernorAlphaPhishingProxy");
    const proxy = await PhishingProxy.connect(attacker).deploy();
    await proxy.waitForDeployment();

    await expect(
      proxy.connect(voter).trick(await governor.getAddress(), proposalId)
    ).to.be.revertedWith("Governor: no voting power");
  });

  it("enforces a timelock delay after voting ends", async function () {
    const proposalId = await createProposal();
    const proposal = await advanceToVotingStart(proposalId);
    await token.setPastVotes(voter.address, proposal.startBlock, PROPOSAL_THRESHOLD);
    await governor.connect(voter).vote(proposalId, true);

    const votingEnd = Number(proposal.endBlock);
    let latest = await ethers.provider.getBlockNumber();
    if (latest <= votingEnd) {
      await mine(votingEnd - latest + 1);
    }

    await expect(governor.execute(proposalId)).to.be.revertedWith("Governor: timelock active");

    const current = await ethers.provider.getBlockNumber();
    const earliestExecutionBlock = Number((await governor.proposals(proposalId)).earliestExecutionBlock);
    if (current < earliestExecutionBlock) {
      await mine(earliestExecutionBlock - current);
    }

    await expect(governor.execute(proposalId)).to.emit(governor, "ProposalExecuted");
    expect(await target.value()).to.equal(42n);
  });
});
