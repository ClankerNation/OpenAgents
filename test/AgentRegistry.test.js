const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry — Issue #172: Frontrunning Fix", function () {
  let registry, owner, user1, user2;

  beforeEach(async function () {
    [owner, user1, user2] = await ethers.getSigners();
    const Registry = await ethers.getContractFactory("AgentRegistry");
    registry = await Registry.deploy(ethers.parseEther("0.01"));
    await registry.waitForDeployment();
  });

  it("two agents same name different sender get different IDs", async function () {
    const fee = ethers.parseEther("0.01");

    // User1 registers "alice"
    const tx1 = await registry.connect(user1).registerAgent("alice", "http://a1", { value: fee });
    const rc1 = await tx1.wait();
    const ev1 = rc1.logs.find(l => l.fragment?.name === "AgentRegistered");

    // User2 registers "alice" — should succeed (different sender)
    const tx2 = await registry.connect(user2).registerAgent("alice", "http://a2", { value: fee });
    const rc2 = await tx2.wait();
    const ev2 = rc2.logs.find(l => l.fragment?.name === "AgentRegistered");

    // IDs must be different
    expect(ev1.args.agentId).to.not.equal(ev2.args.agentId);
  });

  it("same sender cannot register same name twice", async function () {
    const fee = ethers.parseEther("0.01");
    await registry.connect(user1).registerAgent("alice", "http://a1", { value: fee });

    // Second registration of same name should revert
    await expect(
      registry.connect(user1).registerAgent("alice", "http://a2", { value: fee })
    ).to.be.revertedWith("Agent name already taken");
  });

  it("nonce increments — same sender same block different names get different IDs", async function () {
    const fee = ethers.parseEther("0.01");

    const tx1 = await registry.connect(user1).registerAgent("bob", "http://b1", { value: fee });
    const rc1 = await tx1.wait();
    const ev1 = rc1.logs.find(l => l.fragment?.name === "AgentRegistered");

    const tx2 = await registry.connect(user1).registerAgent("charlie", "http://c1", { value: fee });
    const rc2 = await tx2.wait();
    const ev2 = rc2.logs.find(l => l.fragment?.name === "AgentRegistered");

    expect(ev1.args.agentId).to.not.equal(ev2.args.agentId);

    // Verify nonce incremented
    expect(await registry.nonce(user1.address)).to.equal(2);
  });

  it("existing registration flow unchanged for honest users", async function () {
    const fee = ethers.parseEther("0.01");
    const tx = await registry.connect(user1).registerAgent("honest", "http://ok", { value: fee });
    const rc = await tx.wait();
    const ev = rc.logs.find(l => l.fragment?.name === "AgentRegistered");

    const agent = await registry.getAgent(ev.args.agentId);
    expect(agent.owner).to.equal(user1.address);
    expect(agent.name).to.equal("honest");
    expect(agent.active).to.be.true;
    expect(agent.reputation).to.equal(100);
  });
});
