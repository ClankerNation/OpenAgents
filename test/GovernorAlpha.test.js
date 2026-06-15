const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("GovernorAlpha", function () {
  let governor, token;
  let owner, admin, proposer, voter1, voter2, nonAdmin;
  const TOTAL_SUPPLY = ethers.parseEther("10000000"); // 10M tokens
  const PROPOSAL_THRESHOLD = ethers.parseEther("100000"); // 100k tokens
  const DEFAULT_QUORUM = TOTAL_SUPPLY * 4n / 100n; // 4% of total supply = 400k tokens

  beforeEach(async function () {
    [owner, admin, proposer, voter1, voter2, nonAdmin] = await ethers.getSigners();

    // Deploy a mock ERC20Votes token
    const MockToken = await ethers.getContractFactory("MockERC20Votes");
    token = await MockToken.deploy("Governance Token", "GOV", TOTAL_SUPPLY);
    await token.waitForDeployment();

    // Deploy GovernorAlpha with admin
    const GovernorAlpha = await ethers.getContractFactory("GovernorAlpha");
    governor = await GovernorAlpha.connect(admin).deploy(await token.getAddress());
    await governor.waitForDeployment();
  });

  it("default quorum is 4% of total supply", async function () {
    const quorum = await governor.quorumVotes();
    expect(quorum).to.equal(DEFAULT_QUORUM);
  });

  it("admin can update quorum", async function () {
    const newQuorum = ethers.parseEther("500000"); // 500k tokens

    await expect(governor.connect(admin).setQuorum(newQuorum))
      .to.emit(governor, "QuorumUpdated")
      .withArgs(DEFAULT_QUORUM, newQuorum);

    const quorum = await governor.quorumVotes();
    expect(quorum).to.equal(newQuorum);
  });

  it("non-admin cannot update quorum", async function () {
    const newQuorum = ethers.parseEther("500000");

    await expect(
      governor.connect(nonAdmin).setQuorum(newQuorum)
    ).to.be.revertedWith("GovernorAlpha: not admin");
  });

  it("execute() reverts when below quorum", async function () {
    // Setup: mint tokens to proposer and voter1, then delegate
    await token.mint(proposer.address, PROPOSAL_THRESHOLD);
    await token.connect(proposer).delegate(proposer.address);

    // Mint insufficient votes to voter1 (below quorum) and delegate before proposal
    await token.mint(voter1.address, ethers.parseEther("1000")); // 1k tokens, way below 400k quorum
    await token.connect(voter1).delegate(voter1.address);

    // Create proposal
    const targets = [await token.getAddress()];
    const values = [0];
    const calldatas = ["0x"];

    await governor.connect(proposer).propose(targets, values, calldatas);
    const proposalId = await governor.proposalCount();

    // Advance to voting period and vote
    await ethers.provider.send("evm_mine");
    await governor.connect(voter1).vote(proposalId, true);

    // Advance past voting period
    for (let i = 0; i < 17282; i++) {
      await ethers.provider.send("evm_mine");
    }

    // Execute should revert due to below quorum
    await expect(
      governor.execute(proposalId)
    ).to.be.revertedWith("GovernorAlpha::execute: below quorum");
  });

  it("execute() succeeds when quorum is met", async function () {
    // Setup: mint tokens to proposer and voter1, then delegate before proposal
    await token.mint(proposer.address, PROPOSAL_THRESHOLD);
    await token.connect(proposer).delegate(proposer.address);

    // Mint sufficient votes to voter1 (above quorum) and delegate before proposal
    const voteAmount = DEFAULT_QUORUM + ethers.parseEther("1000"); // quorum + margin
    await token.mint(voter1.address, voteAmount);
    await token.connect(voter1).delegate(voter1.address);

    // Create proposal with a simple no-op target (the governor itself)
    const targets = [await governor.getAddress()];
    const values = [0];
    const calldatas = ["0x"];

    await governor.connect(proposer).propose(targets, values, calldatas);
    const proposalId = await governor.proposalCount();

    // Advance to voting period and vote
    await ethers.provider.send("evm_mine");
    await governor.connect(voter1).vote(proposalId, true);

    // Advance past voting period
    for (let i = 0; i < 17282; i++) {
      await ethers.provider.send("evm_mine");
    }

    // Execute should succeed
    await expect(governor.execute(proposalId))
      .to.emit(governor, "ProposalExecuted")
      .withArgs(proposalId);

    const p = await governor.proposals(proposalId);
    expect(p.executed).to.be.true;
  });
});
