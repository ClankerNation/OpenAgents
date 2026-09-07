const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("GovernorAlpha Quorum", function () {
  let governor;
  let token;
  let admin;
  let voter1;
  let voter2;

  const PROPOSAL_THRESHOLD = ethers.parseUnits("100000", 18);

  beforeEach(async function () {
    [admin, voter1, voter2] = await ethers.getSigners();

    // Deploy mock ERC20Votes token
    const MockToken = await ethers.getContractFactory("ERC20Votes", admin);
    token = await MockToken.deploy();

    // Mint tokens to voters
    await token.mint(admin.address, PROPOSAL_THRESHOLD * 10n);
    await token.mint(voter1.address, PROPOSAL_THRESHOLD * 5n);
    await token.mint(voter2.address, PROPOSAL_THRESHOLD * 5n);
    await token.connect(admin).delegate(admin.address);
    await token.connect(voter1).delegate(voter1.address);
    await token.connect(voter2).delegate(voter2.address);

    // Deploy GovernorAlpha
    const GovernorAlpha = await ethers.getContractFactory("GovernorAlpha", admin);
    governor = await GovernorAlpha.deploy(token.target);

    // Transfer some ETH for execution
    await admin.sendTransaction({ to: governor.target, value: ethers.parseEther("1") });
  });

  async function createAndAdvanceProposal(targets, values, calldatas) {
    // Move past voting delay
    await time.advanceBlock();
    const tx = await governor.connect(voter1).propose(targets, values, calldatas);
    const receipt = await tx.wait();
    const proposalId = receipt.logs[0].args[0];
    return proposalId;
  }

  async function voteAndAdvance(proposalId, voter, support) {
    await time.advanceBlock();
    await governor.connect(voter).vote(proposalId, support);
    // Advance past voting period
    for (let i = 0; i < 17280 + 10; i++) {
      await time.advanceBlock();
    }
  }

  describe("quorum enforcement", function () {
    it("reverts if forVotes < quorumVotes", async function () {
      // voter1 creates proposal with zero-value call
      const targets = [admin.address];
      const values = [0];
      const calldatas = ["0x"];
      const proposalId = await createAndAdvanceProposal(targets, values, calldatas);

      // voter1 votes FOR but votes are below quorum (quorum is 4% of 20M = 800K tokens, voter1 has 500K)
      await governor.connect(voter1).vote(proposalId, true);
      await time.advanceBlockTo((await ethers.provider.getBlockNumber()) + 17290);

      // Execution should revert due to quorum not reached
      await expect(governor.execute(proposalId)).to.be.revertedWith("Governor: quorum not reached");
    });

    it("executes successfully if forVotes >= quorumVotes", async function () {
      // Create a simple no-op proposal
      const targets = [admin.address];
      const values = [0];
      const calldatas = ["0x"];
      const proposalId = await createAndAdvanceProposal(targets, values, calldatas);

      // Both voters vote FOR — total 1M tokens > quorum (800K)
      await governor.connect(voter1).vote(proposalId, true);
      await governor.connect(voter2).vote(proposalId, true);
      await time.advanceBlockTo((await ethers.provider.getBlockNumber()) + 17290);

      // Execution should succeed
      await expect(governor.execute(proposalId)).to.not.be.reverted;
    });

    it("reverts if forVotes <= againstVotes even if quorum met", async function () {
      const targets = [admin.address];
      const values = [0];
      const calldatas = ["0x"];
      const proposalId = await createAndAdvanceProposal(targets, values, calldatas);

      // voter1 votes FOR, voter2 votes AGAINST
      await governor.connect(voter1).vote(proposalId, true);
      await governor.connect(voter2).vote(proposalId, false);
      await time.advanceBlockTo((await ethers.provider.getBlockNumber()) + 17290);

      await expect(governor.execute(proposalId)).to.be.revertedWith("Governor: proposal defeated");
    });
  });

  describe("admin quorum update", function () {
    it("admin can update quorum basis points", async function () {
      const newBps = 200; // 2%
      await expect(governor.connect(admin).updateQuorumBps(newBps))
        .to.emit(governor, "QuorumUpdated");

      // quorumVotes should now be 2% of total supply
      const totalSupply = await token.totalSupply();
      const expectedQuorum = (totalSupply * 200n) / 10000n;
      expect(await governor.quorumVotes()).to.equal(expectedQuorum);
    });

    it("non-admin cannot update quorum", async function () {
      await expect(governor.connect(voter1).updateQuorumBps(500)).to.be.revertedWith("Governor: not admin");
    });
  });
});
