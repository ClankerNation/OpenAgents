const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("GovernorAlpha — Quorum Validation (#180)", function () {
  let governor;
  let token;
  let admin;
  let alice;
  let bob;
  const THRESHOLD = ethers.parseEther("100000");
  const VOTING_DELAY = 1;

  before(async function () {
    [admin, alice, bob] = await ethers.getSigners();
  });

  beforeEach(async function () {
    // Deploy a mock governance token with ERC20Votes
    const GovToken = await ethers.getContractFactory("AgentToken");
    token = await GovToken.deploy("Governance Token", "GOV", ethers.parseEther("1000000"));
    await token.waitForDeployment();

    // Mint voting power to alice
    const mintTx = await token.mint(alice.address, THRESHOLD);
    await mintTx.wait();

    // Delegate votes
    await token.connect(alice).delegate(alice.address);

    // Advance 1 block so getPastVotes works
    await ethers.provider.send("evm_mine", []);

    const GovernorAlpha = await ethers.getContractFactory("GovernorAlpha");
    governor = await GovernorAlpha.deploy(await token.getAddress());
    await governor.waitForDeployment();
  });

  it("should set admin to deployer and default quorum to PROPOSAL_THRESHOLD", async function () {
    expect(await governor.admin()).to.equal(admin.address);
    expect(await governor.quorumVotes()).to.equal(THRESHOLD);
  });

  it("should revert execute if forVotes < quorum", async function () {
    // Create a proposal
    const tx = await governor.connect(alice).propose(
      [alice.address],
      [0],
      ["0x"]
    );
    const receipt = await tx.wait();

    // Vote — alice has exactly THRESHOLD, so 1 for, 0 against
    // Mine past VOTING_DELAY to enter voting
    await ethers.provider.send("evm_mine", []);

    // Vote for
    await governor.connect(alice).vote(1, true);

    // Now raise quorum above alice's votes
    await governor.connect(admin).setQuorumVotes(THRESHOLD + 1n);

    // Mine past voting period
    for (let i = 0; i < 17281; i++) {
      await ethers.provider.send("evm_mine", []);
    }

    // Execute should revert
    await expect(
      governor.execute(1)
    ).to.be.revertedWith("Governor: below quorum");
  });

  it("should execute successfully when forVotes >= quorum", async function () {
    const tx = await governor.connect(alice).propose(
      [alice.address],
      [0],
      ["0x"]
    );
    await tx.wait();

    await ethers.provider.send("evm_mine", []);
    await governor.connect(alice).vote(1, true);

    // Quorum is THRESHOLD, alice has THRESHOLD — exactly at quorum
    for (let i = 0; i < 17281; i++) {
      await ethers.provider.send("evm_mine", []);
    }

    await expect(governor.execute(1)).to.not.be.reverted;
  });

  it("should allow admin to update quorum", async function () {
    const oldQuorum = await governor.quorumVotes();
    const newQuorum = ethers.parseEther("200000");

    await expect(governor.connect(admin).setQuorumVotes(newQuorum))
      .to.emit(governor, "QuorumUpdated")
      .withArgs(oldQuorum, newQuorum);

    expect(await governor.quorumVotes()).to.equal(newQuorum);
  });

  it("should revert if non-admin tries to update quorum", async function () {
    await expect(
      governor.connect(alice).setQuorumVotes(ethers.parseEther("50000"))
    ).to.be.revertedWith("Governor: not admin");
  });

  it("should revert if quorum set to zero", async function () {
    await expect(
      governor.connect(admin).setQuorumVotes(0)
    ).to.be.revertedWith("Governor: quorum cannot be zero");
  });

  it("should execute when forVotes > againstVotes AND forVotes >= quorum", async function () {
    // Give bob voting power too
    const mintTx = await token.mint(bob.address, ethers.parseEther("50000"));
    await mintTx.wait();
    await token.connect(bob).delegate(bob.address);
    await ethers.provider.send("evm_mine", []);

    // Set quorum lower than alice's votes
    await governor.connect(admin).setQuorumVotes(ethers.parseEther("50000"));

    const tx = await governor.connect(alice).propose(
      [alice.address],
      [0],
      ["0x"]
    );
    await tx.wait();
    await ethers.provider.send("evm_mine", []);

    // Alice votes FOR, Bob votes AGAINST — but alice still has more + above quorum
    await governor.connect(alice).vote(1, true);
    await governor.connect(bob).vote(1, false);

    for (let i = 0; i < 17281; i++) {
      await ethers.provider.send("evm_mine", []);
    }

    await expect(governor.execute(1)).to.not.be.reverted;
  });
});
