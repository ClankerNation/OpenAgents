const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("GovernorAlpha — Quorum Validation (Issue #180)", function () {
  let governor, token;
  let admin, proposer, voter1, voter2, voter3;

  const DEFAULT_QUORUM = ethers.utils.parseEther("40000000"); // 40M tokens
  const PROPOSAL_THRESHOLD = ethers.utils.parseEther("100000"); // 100K tokens
  const NOOP_CALLDATA = "0x";

  before(async function () {
    [admin, proposer, voter1, voter2, voter3] = await ethers.getSigners();

    // Deploy ERC20Votes token
    const Token = await ethers.getContractFactory("AgentToken"); // ERC20Votes-extending token in repo
    token = await Token.deploy("AgentToken", "AGENT");
    await token.deployed();

    // Deploy GovernorAlpha
    const GovernorAlpha = await ethers.getContractFactory("GovernorAlpha");
    governor = await GovernorAlpha.deploy(token.address);
    await governor.deployed();

    // admin is the deployer (msg.sender at constructor)
  });

  describe("Quorum Enforcement", function () {
    beforeEach(async function () {
      // Fresh proposal setup for each test
      // Mint tokens and delegate to voters
      const mintAmount = ethers.utils.parseEther("10000000"); // 10M tokens each
      await token.mint(proposer.address, PROPOSAL_THRESHOLD.add(mintAmount));
      await token.mint(voter1.address, mintAmount);
      await token.mint(voter2.address, mintAmount);
      await token.mint(voter3.address, mintAmount);

      await token.connect(proposer).delegate(proposer.address);
      await token.connect(voter1).delegate(voter1.address);
      await token.connect(voter2).delegate(voter2.address);
      await token.connect(voter3).delegate(voter3.address);

      // Advance to next block so delegation takes effect
      await ethers.provider.send("evm_mine");
    });

    it("should revert execute when forVotes is below quorum", async function () {
      // Create proposal
      const tx = await governor.connect(proposer).propose(
        [token.address],
        [0],
        [NOOP_CALLDATA]
      );
      const receipt = await tx.wait();
      const proposalId = 1;

      // Advance past voting delay + period
      await ethers.provider.send("evm_increaseTime", [259200 + 15]); // 3 days + 15s
      await ethers.provider.send("evm_mine");

      // Vote with voter1 — 10M votes, below 40M quorum
      await governor.connect(voter1).vote(proposalId, true);

      // Advance past endBlock
      await ethers.provider.send("evm_increaseTime", [1]);
      await ethers.provider.send("evm_mine");

      // Execute should revert due to below quorum
      await expect(
        governor.connect(proposer).execute(proposalId)
      ).to.be.revertedWith("Governor: below quorum");
    });

    it("should allow execute when forVotes meets quorum", async function () {
      const tx = await governor.connect(proposer).propose(
        [token.address],
        [0],
        [NOOP_CALLDATA]
      );
      await tx.wait();
      const proposalId = 1;

      // Advance past voting delay
      await ethers.provider.send("evm_increaseTime", [15]); // 1 block delay
      await ethers.provider.send("evm_mine");

      // 5 voters: 10M each = 50M > 40M quorum
      await governor.connect(voter1).vote(proposalId, true);
      await governor.connect(voter2).vote(proposalId, true);
      await governor.connect(voter3).vote(proposalId, true);
      // proposer also votes
      await governor.connect(proposer).vote(proposalId, true);

      // Advance past end of voting period
      await ethers.provider.send("evm_increaseTime", [259200]);
      await ethers.provider.send("evm_mine");

      await expect(
        governor.connect(proposer).execute(proposalId)
      ).to.emit(governor, "ProposalExecuted")
        .withArgs(proposalId);
    });

    it("should revert execute on defeated proposal (more against than for)", async function () {
      const tx = await governor.connect(proposer).propose(
        [token.address],
        [0],
        [NOOP_CALLDATA]
      );
      await tx.wait();
      const proposalId = 1;

      await ethers.provider.send("evm_increaseTime", [15]);
      await ethers.provider.send("evm_mine");

      // Voter1 votes for, voter2+3 vote against = defeated
      await governor.connect(voter1).vote(proposalId, true);
      await governor.connect(voter2).vote(proposalId, false);
      await governor.connect(voter3).vote(proposalId, false);
      await governor.connect(proposer).vote(proposalId, false);

      await ethers.provider.send("evm_increaseTime", [259200]);
      await ethers.provider.send("evm_mine");

      await expect(
        governor.connect(proposer).execute(proposalId)
      ).to.be.revertedWith("Governor: proposal defeated");
    });
  });

  describe("Admin Quorum Management", function () {
    it("should initialize with DEFAULT_QUORUM_VOTES", async function () {
      expect(await governor.quorumVotes()).to.equal(DEFAULT_QUORUM);
    });

    it("should allow admin to update quorum", async function () {
      const newQuorum = ethers.utils.parseEther("80000000"); // 80M
      await expect(
        governor.connect(admin).setQuorum(newQuorum)
      ).to.emit(governor, "QuorumUpdated")
        .withArgs(DEFAULT_QUORUM, newQuorum);

      expect(await governor.quorumVotes()).to.equal(newQuorum);
    });

    it("should revert when non-admin tries to update quorum", async function () {
      const newQuorum = ethers.utils.parseEther("80000000");
      await expect(
        governor.connect(proposer).setQuorum(newQuorum)
      ).to.be.revertedWith("Governor: not admin");
    });

    it("should revert setting quorum to zero", async function () {
      await expect(
        governor.connect(admin).setQuorum(0)
      ).to.be.revertedWith("Governor: zero quorum");
    });

    it("should allow admin to transfer admin role", async function () {
      await governor.connect(admin).setAdmin(proposer.address);
      expect(await governor.admin()).to.equal(proposer.address);
    });

    it("should revert setting admin to zero address", async function () {
      await expect(
        governor.connect(admin).setAdmin(ethers.constants.AddressZero)
      ).to.be.revertedWith("Governor: zero address");
    });

    it("should allow new admin to update quorum after transfer", async function () {
      await governor.connect(admin).setAdmin(proposer.address);
      const newQuorum = ethers.utils.parseEther("50000000");
      await expect(
        governor.connect(proposer).setQuorum(newQuorum)
      ).to.emit(governor, "QuorumUpdated");

      expect(await governor.quorumVotes()).to.equal(newQuorum);
    });
  });

  describe("Backwards Compatibility", function () {
    it("should still allow propose/vote/execute flow unchanged when quorum met", async function () {
      // Full end-to-end: propose → vote → execute with quorum met
      const tx = await governor.connect(proposer).propose(
        [token.address],
        [0],
        [NOOP_CALLDATA]
      );
      await tx.wait();
      const proposalId = 1;

      await ethers.provider.send("evm_increaseTime", [15]);
      await ethers.provider.send("evm_mine");

      // Cast enough votes to meet quorum (4 voters × 10M = 40M = quorum)
      await governor.connect(voter1).vote(proposalId, true);
      await governor.connect(voter2).vote(proposalId, true);
      await governor.connect(voter3).vote(proposalId, true);
      await governor.connect(proposer).vote(proposalId, true);

      await ethers.provider.send("evm_increaseTime", [259200]);
      await ethers.provider.send("evm_mine");

      await expect(
        governor.connect(proposer).execute(proposalId)
      ).to.emit(governor, "ProposalExecuted");

      // Verify executed flag
      const proposal = await governor.proposals(proposalId);
      expect(proposal.executed).to.be.true;
    });
  });
});
