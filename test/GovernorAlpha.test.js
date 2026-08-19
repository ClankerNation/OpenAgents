const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("GovernorAlpha Quorum", function () {
  let governor, token;
  let admin, proposer, voter1, voter2, voter3;
  const TOTAL_SUPPLY = ethers.parseEther("1000000"); // 1M tokens
  const PROPOSAL_THRESHOLD = ethers.parseEther("100000");
  const QUORUM_VOTES = ethers.parseEther("40000"); // 4% of 1M

  beforeEach(async function () {
    [admin, proposer, voter1, voter2, voter3] = await ethers.getSigners();

    const TokenFactory = await ethers.getContractFactory("MockERC20Votes");
    token = await TokenFactory.deploy("GovToken", "GOV");
    await token.waitForDeployment();

    // Mint tokens and delegate
    await token.mint(proposer.address, PROPOSAL_THRESHOLD);
    await token.mint(voter1.address, ethers.parseEther("30000")); // 3%
    await token.mint(voter2.address, ethers.parseEther("30000")); // 3%
    await token.mint(voter3.address, ethers.parseEther("10000")); // 1%

    await token.connect(proposer).delegate(proposer.address);
    await token.connect(voter1).delegate(voter1.address);
    await token.connect(voter2).delegate(voter2.address);
    await token.connect(voter3).delegate(voter3.address);

    const GovernorFactory = await ethers.getContractFactory("GovernorAlpha");
    governor = await GovernorFactory.deploy(token.target, QUORUM_VOTES);
    await governor.waitForDeployment();

    // Mine a block so votes are registered in past blocks
    await ethers.provider.send("evm_mine");
  });

  async function createAndVote(voters, support) {
    const targets = [admin.address];
    const values = [0];
    const calldatas = ["0x"];
    
    const tx = await governor.connect(proposer).propose(targets, values, calldatas);
    const receipt = await tx.wait();
    const proposalId = await governor.proposalCount();

    // Advance to start block
    await ethers.provider.send("evm_mine");
    await ethers.provider.send("evm_mine");

    for (const voter of voters) {
      await governor.connect(voter).vote(proposalId, support);
    }

    // Advance past end block
    for (let i = 0; i < 17282; i++) {
      await ethers.provider.send("evm_mine");
    }

    return proposalId;
  }

  it("should revert execution if below quorum", async function () {
    // Only voter3 (1%) votes FOR. Total 1% < 4% quorum.
    const proposalId = await createAndVote([voter3], true);
    
    await expect(
      governor.connect(admin).execute(proposalId)
    ).to.be.revertedWith("Governor: below quorum");
  });

  it("should allow execution if at or above quorum", async function () {
    // voter1 (3%) + voter3 (1%) = 4% FOR. Meets quorum.
    const proposalId = await createAndVote([voter1, voter3], true);
    
    await expect(
      governor.connect(admin).execute(proposalId)
    ).to.emit(governor, "ProposalExecuted");
  });

  it("should allow admin to update quorum", async function () {
    const newQuorum = ethers.parseEther("50000"); // 5%
    await expect(governor.connect(admin).setQuorum(newQuorum))
      .to.emit(governor, "QuorumUpdated")
      .withArgs(QUORUM_VOTES, newQuorum);
      
    expect(await governor.quorumVotes()).to.equal(newQuorum);
  });

  it("should reject non-admin updating quorum", async function () {
    await expect(
      governor.connect(voter1).setQuorum(ethers.parseEther("50000"))
    ).to.be.revertedWith("Governor: not admin");
  });
});
