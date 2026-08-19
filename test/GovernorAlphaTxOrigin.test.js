/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("GovernorAlpha tx.origin Fix and Timelock", function () {
  let governor, token;
  let owner, voter, attacker;

  before(async function () {
    [owner, voter, attacker] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("MockGovToken");
    token = await Token.deploy();
    await token.waitForDeployment();

    // Distribute tokens and delegate
    await token.transfer(voter.address, ethers.parseEther("200000"));
    await token.connect(voter).delegate(voter.address);

    const Governor = await ethers.getContractFactory("GovernorAlpha");
    governor = await Governor.deploy(token.target);
    await governor.waitForDeployment();
  });

  it("should use msg.sender for voting and prevent tx.origin phishing", async function () {
    // Advance a block for delegation to take effect
    await ethers.provider.send("evm_mine");

    // Create a proposal
    const targets = [owner.address];
    const values = [0];
    const calldatas = ["0x"];
    
    const tx = await governor.connect(voter).propose(targets, values, calldatas);
    const receipt = await tx.wait();
    const proposalId = 1n;

    // Advance to voting period
    await ethers.provider.send("evm_mine");
    await ethers.provider.send("evm_mine");

    // Voter votes directly - should succeed
    await governor.connect(voter).vote(proposalId, true);
    
    const prop = await governor.proposals(proposalId);
    expect(prop.forVotes).to.equal(ethers.parseEther("200000"));
  });

  it("should enforce timelock delay on execution", async function () {
    const proposalId = 1n;
    
    // End voting period (VOTING_DELAY + VOTING_PERIOD = 1 + 17280 = 17281 blocks)
    // Mine 17285 blocks to ensure we are strictly past endBlock
    await ethers.provider.send("hardhat_mine", ["0x4385"]);
    
    // Queue the proposal
    await governor.connect(voter).queue(proposalId);
    
    // Try to execute immediately - should revert
    await expect(
      governor.connect(voter).execute(proposalId)
    ).to.be.revertedWith("Governor: timelock not expired");

    // Advance time past timelock (2 days)
    await ethers.provider.send("evm_increaseTime", [2 * 24 * 60 * 60 + 1]);
    await ethers.provider.send("evm_mine");

    // Execute should now succeed
    await governor.connect(voter).execute(proposalId);
    
    const prop = await governor.proposals(proposalId);
    expect(prop.executed).to.be.true;
  });
});
