// @generated-by szamaniai-agent
// @timestamp 2026-06-09T06:15:00Z
// @runtime os=linux arch=x64 home=/root wd=/tmp/OpenAgents shell=bash
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry", function () {
  let registry;
  let owner, alice, bob;

  beforeEach(async function () {
    [owner, alice, bob] = await ethers.getSigners();
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(ethers.utils.parseEther("0.01"));
    await registry.deployed();
  });

  it("should register an agent with a unique ID", async function () {
    const tx = await registry.connect(alice).registerAgent("agent-alpha", "https://agent-alpha.example.com", { value: ethers.utils.parseEther("0.01") });
    const receipt = await tx.wait();

    // Agent ID should be the first (1)
    const agentId = ethers.utils.hexZeroPad("0x01", 32);
    const agent = await registry.getAgent(agentId);
    expect(agent.owner).to.equal(alice.address);
    expect(agent.name).to.equal("agent-alpha");
    expect(agent.active).to.equal(true);
    expect(agent.registeredAt).to.be.gt(0);
  });

  it("should assign different IDs for same name + same block registerations", async function () {
    // Register two agents with same name in same block via different callers
    const tx1 = await registry.connect(alice).registerAgent("same-name", "https://alice.example.com", { value: ethers.utils.parseEther("0.01") });
    const tx2 = await registry.connect(bob).registerAgent("same-name", "https://bob.example.com", { value: ethers.utils.parseEther("0.01") });

    const receipt1 = await tx1.wait();
    const receipt2 = await tx2.wait();

    // Counter-based IDs should be sequential (bytes32(1) and bytes32(2))
    const id1 = ethers.utils.hexZeroPad("0x01", 32);
    const id2 = ethers.utils.hexZeroPad("0x02", 32);

    // Verify first agent
    const agent1 = await registry.getAgent(id1);
    expect(agent1.owner).to.equal(alice.address);
    expect(agent1.name).to.equal("same-name");

    // Verify second agent
    const agent2 = await registry.getAgent(id2);
    expect(agent2.owner).to.equal(bob.address);
    expect(agent2.name).to.equal("same-name");

    // IDs must be different
    expect(id1).to.not.equal(id2);
  });

  it("should enforce minimum registration fee", async function () {
    await expect(
      registry.connect(alice).registerAgent("cheap-agent", "https://example.com", { value: ethers.utils.parseEther("0.001") })
    ).to.be.revertedWith("Insufficient fee");
  });

  it("should reject empty name", async function () {
    await expect(
      registry.connect(alice).registerAgent("", "https://example.com", { value: ethers.utils.parseEther("0.01") })
    ).to.be.revertedWith("Invalid name");
  });

  it("should reject name over 64 characters", async function () {
    const longName = "a".repeat(65);
    await expect(
      registry.connect(alice).registerAgent(longName, "https://example.com", { value: ethers.utils.parseEther("0.01") })
    ).to.be.revertedWith("Invalid name");
  });

  it("should allow deactivation by agent owner", async function () {
    await registry.connect(alice).registerAgent("agent-alpha", "https://example.com", { value: ethers.utils.parseEther("0.01") });
    const agentId = ethers.utils.hexZeroPad("0x01", 32);

    await registry.connect(alice).deactivateAgent(agentId);
    const agent = await registry.getAgent(agentId);
    expect(agent.active).to.equal(false);
  });

  it("should prevent non-owner deactivation", async function () {
    await registry.connect(alice).registerAgent("agent-alpha", "https://example.com", { value: ethers.utils.parseEther("0.01") });
    const agentId = ethers.utils.hexZeroPad("0x01", 32);

    await expect(
      registry.connect(bob).deactivateAgent(agentId)
    ).to.be.revertedWith("Not agent owner");
  });

  it("should track active agent count", async function () {
    await registry.connect(alice).registerAgent("agent-1", "https://ex1.com", { value: ethers.utils.parseEther("0.01") });
    await registry.connect(bob).registerAgent("agent-2", "https://ex2.com", { value: ethers.utils.parseEther("0.01") });

    let count = await registry.getActiveAgentCount();
    expect(count).to.equal(2);

    // Deactivate one
    const agentId1 = ethers.utils.hexZeroPad("0x01", 32);
    await registry.connect(alice).deactivateAgent(agentId1);

    count = await registry.getActiveAgentCount();
    expect(count).to.equal(1);
  });

  it("should allow owner to update reputation", async function () {
    await registry.connect(alice).registerAgent("agent-alpha", "https://example.com", { value: ethers.utils.parseEther("0.01") });
    const agentId = ethers.utils.hexZeroPad("0x01", 32);

    await registry.connect(owner).updateReputation(agentId, 50);
    const agent = await registry.getAgent(agentId);
    expect(agent.reputation).to.equal(150); // 100 base + 50
  });

  it("should allow owner to withdraw fees", async function () {
    await registry.connect(alice).registerAgent("agent-alpha", "https://example.com", { value: ethers.utils.parseEther("0.01") });

    const balanceBefore = await ethers.provider.getBalance(owner.address);
    const tx = await registry.connect(owner).withdrawFees();
    const receipt = await tx.wait();
    const gasCost = receipt.gasUsed.mul(receipt.effectiveGasPrice);
    const balanceAfter = await ethers.provider.getBalance(owner.address);

    // Balance should have increased by fee minus gas costs
    expect(balanceAfter.add(gasCost)).to.be.gt(balanceBefore);
  });
});
