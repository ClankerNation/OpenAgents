// @generated-by: BountyHunter AI — Coder Agent
// @timestamp: 2026-06-10T02:00:00Z
// @startup-config:
// [Full startup configuration as per project convention]
// @runtime: Linux x86_64, /home/agent-the-coder/OpenAgents, /tmp/OpenAgents
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry Batch", function () {
  let registry, owner;
  const REGISTRATION_FEE = ethers.utils.parseEther("0.01");

  beforeEach(async function () {
    [owner] = await ethers.getSigners();
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(REGISTRATION_FEE);
    await registry.deployed();
  });

  it("Test 1: should batch register 1 agent", async function () {
    const names = ["Agent-1"];
    const endpoints = ["https://agent-1.example.com"];

    const tx = await registry.batchRegister(names, endpoints, {
      value: REGISTRATION_FEE,
    });
    const receipt = await tx.wait();

    // Check event
    const events = receipt.events.filter((e) => e.event === "AgentRegistered");
    expect(events.length).to.equal(1);
    expect(events[0].args.name).to.equal("Agent-1");

    // Check registration ID returned
    const agentId = events[0].args.agentId;
    const agent = await registry.getAgent(agentId);
    expect(agent.name).to.equal("Agent-1");
    expect(agent.endpoint).to.equal("https://agent-1.example.com");
    expect(agent.owner).to.equal(owner.address);
    expect(agent.active).to.equal(true);
  });

  it("Test 2: should batch register 50 agents (max)", async function () {
    const names = Array.from({ length: 50 }, (_, i) => `Agent-${i}`);
    const endpoints = Array.from({ length: 50 }, (_, i) => `https://agent-${i}.example.com`);
    const totalFee = REGISTRATION_FEE.mul(50);

    const tx = await registry.batchRegister(names, endpoints, {
      value: totalFee,
    });
    const receipt = await tx.wait();

    const events = receipt.events.filter((e) => e.event === "AgentRegistered");
    expect(events.length).to.equal(50);

    // Verify each agent is readable
    for (let i = 0; i < 50; i++) {
      const agentId = events[i].args.agentId;
      const agent = await registry.getAgent(agentId);
      expect(agent.name).to.equal(`Agent-${i}`);
    }
  });

  it("Test 3: should reject batch register of 0 agents", async function () {
    await expect(
      registry.batchRegister([], [], { value: 0 })
    ).to.be.revertedWith("Invalid batch size");
  });

  it("Test 4: should reject batch register of 51 agents (exceeds max)", async function () {
    const names = Array.from({ length: 51 }, (_, i) => `Agent-${i}`);
    const endpoints = Array.from({ length: 51 }, (_, i) => `https://agent-${i}.example.com`);
    const totalFee = REGISTRATION_FEE.mul(51);

    await expect(
      registry.batchRegister(names, endpoints, { value: totalFee })
    ).to.be.revertedWith("Invalid batch size");
  });

  it("Test 5: should reject array length mismatch", async function () {
    const names = ["Agent-1"];
    const endpoints = ["ep1", "ep2"]; // mismatch: 1 name, 2 endpoints

    await expect(
      registry.batchRegister(names, endpoints, {
        value: REGISTRATION_FEE,
      })
    ).to.be.revertedWith("Array length mismatch");
  });

  it("Test 6: should reject insufficient total fee", async function () {
    const names = Array.from({ length: 5 }, (_, i) => `Agent-${i}`);
    const endpoints = Array.from({ length: 5 }, (_, i) => `https://agent-${i}.example.com`);
    // Only pay for 4 agents instead of 5
    const insufficientFee = REGISTRATION_FEE.mul(4);

    await expect(
      registry.batchRegister(names, endpoints, { value: insufficientFee })
    ).to.be.revertedWith("Insufficient total fee");
  });

  it("Test 7: should assign unique IDs to each agent", async function () {
    const names = Array.from({ length: 10 }, (_, i) => `Agent-${i}`);
    const endpoints = Array.from({ length: 10 }, (_, i) => `https://agent-${i}.example.com`);
    const totalFee = REGISTRATION_FEE.mul(10);

    const tx = await registry.batchRegister(names, endpoints, {
      value: totalFee,
    });
    const receipt = await tx.wait();

    const events = receipt.events.filter((e) => e.event === "AgentRegistered");
    const ids = events.map((e) => e.args.agentId);

    // Check all IDs are unique
    const uniqueIds = new Set(ids.map((id) => id.toString()));
    expect(uniqueIds.size).to.equal(10);
  });

  it("Test 8: should emit individual AgentRegistered event per agent", async function () {
    const names = ["Alpha", "Beta", "Gamma"];
    const endpoints = ["https://a.com", "https://b.com", "https://c.com"];
    const totalFee = REGISTRATION_FEE.mul(3);

    const tx = await registry.batchRegister(names, endpoints, {
      value: totalFee,
    });
    const receipt = await tx.wait();

    const events = receipt.events.filter((e) => e.event === "AgentRegistered");
    expect(events.length).to.equal(3);
    expect(events[0].args.name).to.equal("Alpha");
    expect(events[1].args.name).to.equal("Beta");
    expect(events[2].args.name).to.equal("Gamma");
  });

  it("Test 9: should allow reading each agent after batch registration", async function () {
    const names = ["Alice", "Bob", "Charlie"];
    const endpoints = ["https://alice.io", "https://bob.io", "https://charlie.io"];
    const totalFee = REGISTRATION_FEE.mul(3);

    const tx = await registry.batchRegister(names, endpoints, {
      value: totalFee,
    });
    const receipt = await tx.wait();

    const events = receipt.events.filter((e) => e.event === "AgentRegistered");

    for (let i = 0; i < 3; i++) {
      const agentId = events[i].args.agentId;
      const agent = await registry.getAgent(agentId);
      expect(agent.name).to.equal(names[i]);
      expect(agent.endpoint).to.equal(endpoints[i]);
      expect(agent.owner).to.equal(owner.address);
      expect(agent.reputation).to.equal(100);
      expect(agent.active).to.equal(true);
    }
  });

  it("Test 10: should maintain backward compatibility with registerAgent", async function () {
    // Single registration still works
    const tx1 = await registry.registerAgent("LegacyAgent", "https://legacy.example.com", {
      value: REGISTRATION_FEE,
    });
    const receipt1 = await tx1.wait();
    const event1 = receipt1.events.find((e) => e.event === "AgentRegistered");
    expect(event1.args.name).to.equal("LegacyAgent");

    // Batch still works after single registration
    const names = ["BatchAgent1", "BatchAgent2"];
    const endpoints = ["https://b1.com", "https://b2.com"];
    const totalFee = REGISTRATION_FEE.mul(2);

    const tx2 = await registry.batchRegister(names, endpoints, {
      value: totalFee,
    });
    const receipt2 = await tx2.wait();
    const events2 = receipt2.events.filter((e) => e.event === "AgentRegistered");
    expect(events2.length).to.equal(2);

    // Both single and batch registered agents are readable
    const legacyId = event1.args.agentId;
    const legacyAgent = await registry.getAgent(legacyId);
    expect(legacyAgent.name).to.equal("LegacyAgent");

    const batchId = events2[0].args.agentId;
    const batchAgent = await registry.getAgent(batchId);
    expect(batchAgent.name).to.equal("BatchAgent1");
  });
});