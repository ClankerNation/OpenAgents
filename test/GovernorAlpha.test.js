const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("GovernorAlpha", function () {
  let token, gov, owner, voter1, voter2, voter3;
  const QUORUM = ethers.parseEther("1000000");
  const PROPOSAL_THRESHOLD = ethers.parseEther("100000");

  beforeEach(async function () {
    [owner, voter1, voter2, voter3] = await ethers.getSigners();

    // Deploy an ERC20Votes token
    const Token = await ethers.getContractFactory("TestVotesToken");
    token = await Token.deploy();
    await token.waitForDeployment();

    // Mint tokens to voters
    // voter1: 5M, voter2: 3M, voter3: 500K (below default 1M test quorum)
    await token.mint(voter1.address, ethers.parseEther("5000000"));
    await token.mint(voter2.address, ethers.parseEther("3000000"));
    await token.mint(voter3.address, ethers.parseEther("500000"));
    await token.mint(owner.address, ethers.parseEther("10000000"));

    // Deploy GovernorAlpha
    const GovernorAlpha = await ethers.getContractFactory("TestGovernorAlpha");
    gov = await GovernorAlpha.deploy(await token.getAddress());
    await gov.waitForDeployment();

    // Delegate votes so getVotes/getPastVotes work
    await token.connect(voter1).delegate(voter1.address);
    await token.connect(voter2).delegate(voter2.address);
    await token.connect(voter3).delegate(voter3.address);
    await token.connect(owner).delegate(owner.address);

    // Mine blocks so delegation takes effect
    await ethers.provider.send("evm_mine");
  });

  describe("Quorum Validation", function () {
    it("should initialize quorumVotes to DEFAULT_QUORUM_VOTES", async function () {
      expect(await gov.quorumVotes()).to.equal(QUORUM);
    });

    it("should revert execute when forVotes below quorum", async function () {
      // Voter3 has only 500K tokens, below 1M test quorum
      await token.connect(voter3).delegate(voter3.address);
      await ethers.provider.send("evm_mine");

      // Create proposal
      const tx = await gov.connect(voter3).propose(
        [voter1.address],
        [0],
        ["0x"]
      );
      const receipt = await tx.wait();
      const proposalId = 1;

      // Advance past voting delay (0 for test)
      // Vote FOR with voter3 (500K tokens — below 1M quorum)
      await gov.connect(voter3).vote(proposalId, true);

      // Advance past voting period (5 blocks)
      for (let i = 0; i < 5; i++) {
        await ethers.provider.send("evm_mine");
      }

      // Execute should revert with "below quorum"
      await expect(
        gov.connect(owner).execute(proposalId)
      ).to.be.revertedWith("Governor: below quorum");
    });

    it("should execute when forVotes at or above quorum", async function () {
      // Voter1 has 5M tokens, above 1M test quorum
      await token.connect(voter1).delegate(voter1.address);
      await ethers.provider.send("evm_mine");

      // Create proposal
      const tx = await gov.connect(voter1).propose(
        [voter1.address],
        [0],
        ["0x"]
      );
      const receipt = await tx.wait();
      const proposalId = 1;

      // Advance past voting delay
      // Vote FOR with voter1 (5M tokens — above 1M quorum)
      await gov.connect(voter1).vote(proposalId, true);

      // Advance past voting period (5 blocks)
      for (let i = 0; i < 5; i++) {
        await ethers.provider.send("evm_mine");
      }

      // Execute should succeed
      await expect(gov.connect(owner).execute(proposalId)).to.not.be.reverted;
      const prop = await gov.proposals(proposalId);
      expect(prop.executed).to.be.true;
    });

    it("should execute when forVotes exceeds quorum and has majority", async function () {
      // voter1 = 5M FOR, voter2 = 3M AGAINST → 5M > 1M quorum AND 5M > 3M
      await token.connect(voter1).delegate(voter1.address);
      await token.connect(voter2).delegate(voter2.address);
      await ethers.provider.send("evm_mine");

      const tx = await gov.connect(voter1).propose(
        [voter1.address],
        [0],
        ["0x"]
      );
      await tx.wait();
      const proposalId = 1;

      await gov.connect(voter1).vote(proposalId, true);
      await gov.connect(voter2).vote(proposalId, false);

      for (let i = 0; i < 5; i++) {
        await ethers.provider.send("evm_mine");
      }

      await expect(gov.connect(owner).execute(proposalId)).to.not.be.reverted;
    });
  });

  describe("Admin Quorum Configuration", function () {
    it("should allow owner to update quorumVotes", async function () {
      const newQuorum = ethers.parseEther("2000000");
      await expect(gov.connect(owner).setQuorumVotes(newQuorum))
        .to.emit(gov, "QuorumVotesUpdated")
        .withArgs(QUORUM, newQuorum);
      expect(await gov.quorumVotes()).to.equal(newQuorum);
    });

    it("should revert when non-owner tries to set quorum", async function () {
      await expect(
        gov.connect(voter1).setQuorumVotes(ethers.parseEther("1000000"))
      ).to.be.revertedWithCustomError(gov, "OwnableUnauthorizedAccount");
    });

    it("should revert when setting quorum to zero", async function () {
      await expect(
        gov.connect(owner).setQuorumVotes(0)
      ).to.be.revertedWith("Governor: zero quorum");
    });

    it("should use updated quorum for execute validation", async function () {
      // Lower quorum to 100K
      await gov.connect(owner).setQuorumVotes(ethers.parseEther("100000"));

      // Voter3 has 500K tokens, above new 100K quorum
      await token.connect(voter3).delegate(voter3.address);
      await ethers.provider.send("evm_mine");

      const tx = await gov.connect(voter3).propose(
        [voter3.address],
        [0],
        ["0x"]
      );
      await tx.wait();
      const proposalId = 1;

      await gov.connect(voter3).vote(proposalId, true);

      for (let i = 0; i < 5; i++) {
        await ethers.provider.send("evm_mine");
      }

      await expect(gov.connect(owner).execute(proposalId)).to.not.be.reverted;
    });
  });

  describe("Vote Security (tx.origin fix)", function () {
    it("should use msg.sender not tx.origin for voting", async function () {
      await token.connect(voter1).delegate(voter1.address);
      await ethers.provider.send("evm_mine");

      const tx = await gov.connect(voter1).propose(
        [voter1.address],
        [0],
        ["0x"]
      );
      await tx.wait();
      const proposalId = 1;

      await ethers.provider.send("evm_mine");
      await gov.connect(voter1).vote(proposalId, true);

      const prop = await gov.proposals(proposalId);
      expect(prop.forVotes).to.equal(ethers.parseEther("5000000"));
    });
  });
});
