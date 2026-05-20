const { expect } = require("chai");
const { ethers, network } = require("hardhat");
const { anyValue } = require("@nomicfoundation/hardhat-chai-matchers/withArgs");

describe("GovernorAlpha cancellation and delegation expiry", function () {
  let token;
  let governor;
  let proposer;
  let delegatee;
  let other;

  beforeEach(async function () {
    [proposer, delegatee, other] = await ethers.getSigners();

    const MockVotesToken = await ethers.getContractFactory("MockVotesToken");
    token = await MockVotesToken.deploy();
    await token.waitForDeployment();

    const GovernorAlpha = await ethers.getContractFactory("GovernorAlpha");
    governor = await GovernorAlpha.deploy(await token.getAddress());
    await governor.waitForDeployment();

    await token.setVotes(proposer.address, ethers.parseEther("500000"));
    await token.setVotes(other.address, ethers.parseEther("500000"));
  });

  async function createProposal() {
    const tx = await governor.connect(proposer).propose([other.address], [0], ["0x"]);
    const receipt = await tx.wait();
    const event = receipt.logs.find((log) => log.fragment && log.fragment.name === "ProposalCreated");
    return event.args.id;
  }

  async function mineToActive() {
    await network.provider.send("hardhat_mine", ["0x2"]);
  }

  it("allows a proposal to be canceled before quorum", async function () {
    const proposalId = await createProposal();

    await expect(governor.connect(other).cancelProposal(proposalId))
      .to.emit(governor, "ProposalCanceled")
      .withArgs(proposalId);

    expect(await governor.state(proposalId)).to.equal(5);
    await expect(governor.connect(proposer).execute(proposalId))
      .to.be.revertedWith("Governor: proposal canceled");
  });

  it("rejects cancellation after quorum has been reached", async function () {
    const proposalId = await createProposal();
    await mineToActive();

    await governor.connect(other).vote(proposalId, true);

    expect(await governor.quorumReached(proposalId)).to.equal(true);
    await expect(governor.cancelProposal(proposalId))
      .to.be.revertedWith("Governor: quorum reached");
  });

  it("expires and auto-revokes delegation records", async function () {
    const now = (await ethers.provider.getBlock("latest")).timestamp;
    const expiry = now + 60;

    await expect(governor.connect(proposer).delegateWithExpiry(delegatee.address, expiry))
      .to.emit(governor, "DelegationSet")
      .withArgs(proposer.address, delegatee.address, expiry);

    expect(await governor.currentDelegate(proposer.address)).to.equal(delegatee.address);
    expect(await governor.delegationHistoryLength(proposer.address)).to.equal(1);

    await network.provider.send("evm_setNextBlockTimestamp", [expiry + 1]);
    await network.provider.send("evm_mine");

    expect(await governor.currentDelegate(proposer.address)).to.equal(ethers.ZeroAddress);
    await expect(governor.revokeExpiredDelegation(proposer.address))
      .to.emit(governor, "DelegationRevoked")
      .withArgs(proposer.address, delegatee.address, anyValue);

    expect(await governor.delegationHistoryLength(proposer.address)).to.equal(2);
    const revoked = await governor.getDelegationHistory(proposer.address, 1);
    expect(revoked.revoked).to.equal(true);
    expect(revoked.delegatee).to.equal(delegatee.address);
  });
});
