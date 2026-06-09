const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry", function () {
  let registry, owner, alice, bob;
  const FEE = ethers.parseEther("0.01");

  beforeEach(async function () {
    [owner, alice, bob] = await ethers.getSigners();
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(FEE);
  });

  describe("registerAgent", function () {
    it("should register an agent with unique ID", async function () {
      const tx = await registry.connect(alice).registerAgent("agent-alpha", "https://alpha.agent", { value: FEE });
      const receipt = await tx.wait();

      const event = receipt.logs.find(log => log.fragment?.name === "AgentRegistered");
      expect(event).to.not.be.undefined;
      const agentId = event.args[0];

      const agent = await registry.getAgent(agentId);
      expect(agent.owner).to.equal(alice.address);
      expect(agent.name).to.equal("agent-alpha");
      expect(agent.active).to.be.true;
    });

    it("should reject registration with insufficient fee", async function () {
      await expect(
        registry.connect(alice).registerAgent("agent", "https://agent.endpoint", { value: 0 })
      ).to.be.revertedWith("Insufficient fee");
    });

    it("should reject empty name", async function () {
      await expect(
        registry.connect(alice).registerAgent("", "https://agent.endpoint", { value: FEE })
      ).to.be.revertedWith("Invalid name");
    });

    it("should reject name longer than 64 bytes", async function () {
      const longName = "a".repeat(65);
      await expect(
        registry.connect(alice).registerAgent(longName, "https://agent.endpoint", { value: FEE })
      ).to.be.revertedWith("Invalid name");
    });
  });

  describe("frontrunning protection", function () {
    it("should assign different IDs for two registrations with same sender, same name, same block", async function () {
      // Disable automine so both txs go into the same block
      await ethers.provider.send("evm_setAutomine", [false]);

      // Submit both transactions without mining between them
      const tx1 = await registry.connect(alice).registerAgent("same-name", "https://agent1.endpoint", { value: FEE });
      const tx2 = await registry.connect(alice).registerAgent("same-name", "https://agent2.endpoint", { value: FEE });

      // Mine the next block (both txs go in the same block)
      await ethers.provider.send("evm_mine", []);

      // Re-enable automine
      await ethers.provider.send("evm_setAutomine", [true]);

      const receipt1 = await tx1.wait();
      const receipt2 = await tx2.wait();

      const event1 = receipt1.logs.find(l => l.fragment?.name === "AgentRegistered");
      const event2 = receipt2.logs.find(l => l.fragment?.name === "AgentRegistered");

      expect(event1).to.not.be.undefined;
      expect(event2).to.not.be.undefined;

      const agentId1 = event1.args[0];
      const agentId2 = event2.args[0];

      // Same block, same sender, same name — but DIFFERENT IDs
      expect(agentId1).to.not.equal(agentId2);

      // Both agents should be retrievable
      const agent1 = await registry.getAgent(agentId1);
      const agent2 = await registry.getAgent(agentId2);
      expect(agent1.owner).to.equal(alice.address);
      expect(agent2.owner).to.equal(alice.address);
      expect(agent1.name).to.equal("same-name");
      expect(agent2.name).to.equal("same-name");
    });

    it("should assign different IDs for different senders with same name in same block", async function () {
      await ethers.provider.send("evm_setAutomine", [false]);

      const tx1 = await registry.connect(alice).registerAgent("popular-name", "https://alice.endpoint", { value: FEE });
      const tx2 = await registry.connect(bob).registerAgent("popular-name", "https://bob.endpoint", { value: FEE });

      await ethers.provider.send("evm_mine", []);
      await ethers.provider.send("evm_setAutomine", [true]);

      const receipt1 = await tx1.wait();
      const receipt2 = await tx2.wait();

      const event1 = receipt1.logs.find(l => l.fragment?.name === "AgentRegistered");
      const event2 = receipt2.logs.find(l => l.fragment?.name === "AgentRegistered");

      expect(event1.args[0]).to.not.equal(event2.args[0]);
    });
  });

  describe("deactivateAgent", function () {
    it("should allow owner to deactivate their agent", async function () {
      const tx = await registry.connect(alice).registerAgent("agent", "https://agent.endpoint", { value: FEE });
      const receipt = await tx.wait();
      const event = receipt.logs.find(l => l.fragment?.name === "AgentRegistered");
      const agentId = event.args[0];

      await registry.connect(alice).deactivateAgent(agentId);
      const agent = await registry.getAgent(agentId);
      expect(agent.active).to.be.false;
    });

    it("should reject deactivation by non-owner", async function () {
      const tx = await registry.connect(alice).registerAgent("agent", "https://agent.endpoint", { value: FEE });
      const receipt = await tx.wait();
      const event = receipt.logs.find(l => l.fragment?.name === "AgentRegistered");
      const agentId = event.args[0];

      await expect(
        registry.connect(bob).deactivateAgent(agentId)
      ).to.be.revertedWith("Not agent owner");
    });
  });

  describe("counter", function () {
    it("should increment nextAgentId after each registration", async function () {
      const id0 = await registry.nextAgentId();
      expect(id0).to.equal(1n);

      await registry.connect(alice).registerAgent("agent-1", "https://a1.endpoint", { value: FEE });
      const id1 = await registry.nextAgentId();
      expect(id1).to.equal(2n);

      await registry.connect(bob).registerAgent("agent-2", "https://a2.endpoint", { value: FEE });
      const id2 = await registry.nextAgentId();
      expect(id2).to.equal(3n);
    });
  });

  describe("owner functions", function () {
    it("should allow owner to update reputation", async function () {
      const tx = await registry.connect(alice).registerAgent("agent", "https://agent.endpoint", { value: FEE });
      const receipt = await tx.wait();
      const event = receipt.logs.find(l => l.fragment?.name === "AgentRegistered");
      const agentId = event.args[0];

      await registry.connect(owner).updateReputation(agentId, 50);
      const agent = await registry.getAgent(agentId);
      expect(agent.reputation).to.equal(150);
    });

    it("should allow owner to withdraw fees", async function () {
      await registry.connect(alice).registerAgent("agent", "https://agent.endpoint", { value: FEE });

      const balanceBefore = await ethers.provider.getBalance(owner.address);
      const tx = await registry.connect(owner).withdrawFees();
      const receipt = await tx.wait();
      const gasCost = receipt.gasUsed * receipt.gasPrice;
      const balanceAfter = await ethers.provider.getBalance(owner.address);

      expect(balanceAfter + gasCost).to.be.gt(balanceBefore);
    });
  });
});
