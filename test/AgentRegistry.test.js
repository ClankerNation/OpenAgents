const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry", function () {
  let registry;
  let owner, user1, user2;
  const REGISTRATION_FEE = ethers.parseEther("0.01");

  before(async function () {
    [owner, user1, user2] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(REGISTRATION_FEE);
    await registry.waitForDeployment();
  });

  // ── Single registration (regression) ──────────────────────────────────

  it("should register a single agent", async function () {
    const tx = await registry.connect(user1).registerAgent("Alice", "https://api.alice.ai", {
      value: REGISTRATION_FEE,
    });
    const receipt = await tx.wait();

    // Check AgentRegistered event
    const events = receipt.logs
      .map((log) => {
        try { return registry.interface.parseLog(log); } catch (_) { return null; }
      })
      .filter(Boolean);
    const regEvent = events.find((e) => e.name === "AgentRegistered");
    expect(regEvent).to.not.be.undefined;
    expect(regEvent.args.name).to.equal("Alice");
    expect(regEvent.args.owner).to.equal(user1.address);

    const agentId = regEvent.args.agentId;
    const agent = await registry.getAgent(agentId);
    expect(agent.name).to.equal("Alice");
    expect(agent.endpoint).to.equal("https://api.alice.ai");
    expect(agent.owner).to.equal(user1.address);
    expect(agent.reputation).to.equal(100n);
    expect(agent.active).to.be.true;
  });

  it("should reject registration with insufficient fee", async function () {
    await expect(
      registry.connect(user1).registerAgent("Bob", "https://api.bob.ai", {
        value: ethers.parseEther("0.001"),
      })
    ).to.be.revertedWith("Insufficient fee");
  });

  it("should reject empty name", async function () {
    await expect(
      registry.connect(user1).registerAgent("", "https://api.empty.ai", {
        value: REGISTRATION_FEE,
      })
    ).to.be.revertedWith("Invalid name");
  });

  it("should reject name longer than 64 bytes", async function () {
    const longName = "A".repeat(65);
    await expect(
      registry.connect(user1).registerAgent(longName, "https://api.long.ai", {
        value: REGISTRATION_FEE,
      })
    ).to.be.revertedWith("Invalid name");
  });

  // ── Batch registration ────────────────────────────────────────────────

  it("should batch-register a single agent", async function () {
    const names = ["Charlie"];
    const endpoints = ["https://api.charlie.ai"];
    const tx = await registry.connect(user2).batchRegister(names, endpoints, {
      value: REGISTRATION_FEE,
    });
    const receipt = await tx.wait();

    const events = receipt.logs
      .map((log) => {
        try { return registry.interface.parseLog(log); } catch (_) { return null; }
      })
      .filter(Boolean);
    const regEvents = events.filter((e) => e.name === "AgentRegistered");
    expect(regEvents.length).to.equal(1);
    expect(regEvents[0].args.name).to.equal("Charlie");
    expect(regEvents[0].args.owner).to.equal(user2.address);

    const agent = await registry.getAgent(regEvents[0].args.agentId);
    expect(agent.name).to.equal("Charlie");
    expect(agent.active).to.be.true;
    expect(agent.reputation).to.equal(100n);
  });

  it("should batch-register 50 agents in one transaction", async function () {
    const names = [];
    const endpoints = [];
    for (let i = 0; i < 50; i++) {
      names.push(`Agent-${i}`);
      endpoints.push(`https://api.agent${i}.ai`);
    }

    const totalFee = REGISTRATION_FEE * 50n;
    const tx = await registry.connect(user1).batchRegister(names, endpoints, {
      value: totalFee,
    });
    const receipt = await tx.wait();

    const events = receipt.logs
      .map((log) => {
        try { return registry.interface.parseLog(log); } catch (_) { return null; }
      })
      .filter(Boolean);
    const regEvents = events.filter((e) => e.name === "AgentRegistered");
    expect(regEvents.length).to.equal(50);

    // Verify each agent is registered
    const ids = [];
    for (let i = 0; i < 50; i++) {
      const ev = regEvents[i];
      expect(ev.args.name).to.equal(`Agent-${i}`);
      expect(ev.args.owner).to.equal(user1.address);
      ids.push(ev.args.agentId);

      const agent = await registry.getAgent(ev.args.agentId);
      expect(agent.active).to.be.true;
      expect(agent.reputation).to.equal(100n);
      expect(agent.owner).to.equal(user1.address);
    }

    // Verify all IDs are unique
    const uniqueIds = new Set(ids.map((id) => id));
    expect(uniqueIds.size).to.equal(50);
  });

  it("should reject batch with array length mismatch", async function () {
    await expect(
      registry.connect(user1).batchRegister(
        ["Agent-A", "Agent-B"],
        ["https://api.a.ai"],
        { value: REGISTRATION_FEE * 2n }
      )
    ).to.be.revertedWith("Array length mismatch");
  });

  it("should reject empty batch", async function () {
    await expect(
      registry.connect(user1).batchRegister([], [], { value: 0 })
    ).to.be.revertedWith("Empty batch");
  });

  it("should reject batch larger than 50", async function () {
    const names = Array(51).fill("Agent");
    const endpoints = Array(51).fill("https://api.agent.ai");
    await expect(
      registry.connect(user1).batchRegister(names, endpoints, {
        value: REGISTRATION_FEE * 51n,
      })
    ).to.be.revertedWith("Batch too large");
  });

  it("should reject batch with invalid name", async function () {
    await expect(
      registry.connect(user1).batchRegister(
        ["Valid", ""],
        ["https://a.ai", "https://b.ai"],
        { value: REGISTRATION_FEE * 2n }
      )
    ).to.be.revertedWith("Invalid name");
  });

  it("should reject batch with insufficient total fee", async function () {
    await expect(
      registry.connect(user1).batchRegister(
        ["Agent-1", "Agent-2"],
        ["https://a.ai", "https://b.ai"],
        { value: REGISTRATION_FEE }
      )
    ).to.be.revertedWith("Insufficient fee");
  });

  it("should collect total fee = registrationFee * count", async function () {
    const count = 3;
    const names = ["F1", "F2", "F3"];
    const endpoints = ["https://f1.ai", "https://f2.ai", "https://f3.ai"];
    const totalFee = REGISTRATION_FEE * BigInt(count);

    const balanceBefore = await ethers.provider.getBalance(registry.target);

    await registry.connect(user1).batchRegister(names, endpoints, {
      value: totalFee,
    });

    const balanceAfter = await ethers.provider.getBalance(registry.target);
    expect(balanceAfter - balanceBefore).to.equal(totalFee);
  });

  // ── Other functions (regression) ──────────────────────────────────────

  it("should deactivate an agent", async function () {
    const tx = await registry.connect(user1).registerAgent("DeactMe", "https://deact.ai", {
      value: REGISTRATION_FEE,
    });
    const receipt = await tx.wait();
    const ev = registry.interface.parseLog(receipt.logs[0]);
    const agentId = ev.args.agentId;

    await registry.connect(user1).deactivateAgent(agentId);
    const agent = await registry.getAgent(agentId);
    expect(agent.active).to.be.false;
  });

  it("should only allow owner to deactivate own agent", async function () {
    const tx = await registry.connect(user1).registerAgent("MyAgent", "https://my.ai", {
      value: REGISTRATION_FEE,
    });
    const receipt = await tx.wait();
    const ev = registry.interface.parseLog(receipt.logs[0]);
    const agentId = ev.args.agentId;

    await expect(
      registry.connect(user2).deactivateAgent(agentId)
    ).to.be.revertedWith("Not agent owner");
  });

  it("should update reputation (owner only)", async function () {
    const tx = await registry.connect(user1).registerAgent("RepAgent", "https://rep.ai", {
      value: REGISTRATION_FEE,
    });
    const receipt = await tx.wait();
    const ev = registry.interface.parseLog(receipt.logs[0]);
    const agentId = ev.args.agentId;

    await registry.connect(owner).updateReputation(agentId, 50);
    let agent = await registry.getAgent(agentId);
    expect(agent.reputation).to.equal(150n);

    await registry.connect(owner).updateReputation(agentId, -200);
    agent = await registry.getAgent(agentId);
    expect(agent.reputation).to.equal(0n); // clamped at 0
  });

  it("should track active agent count", async function () {
    const countBefore = await registry.getActiveAgentCount();
    expect(countBefore).to.be.gte(0);

    await registry.connect(user1).registerAgent("CountMe", "https://count.ai", {
      value: REGISTRATION_FEE,
    });

    const countAfter = await registry.getActiveAgentCount();
    expect(countAfter).to.equal(countBefore + 1n);
  });

  it("should reject non-owner setting registration fee", async function () {
    await expect(
      registry.connect(user1).setRegistrationFee(0)
    ).to.be.revertedWithCustomError(registry, "OwnableUnauthorizedAccount");
  });
});
