const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry batchRegister", function () {
  let registry, owner, user;

  const FEE = ethers.utils.parseEther("0.01");

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners();
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(FEE);
    await registry.deployed();
  });

  describe("batchRegister", function () {
    it("should register a batch of 3 agents", async function () {
      const names = ["Agent-Alpha", "Agent-Bravo", "Agent-Charlie"];
      const endpoints = ["https://a.api", "https://b.api", "https://c.api"];
      const totalFee = FEE.mul(3);

      const tx = await registry.connect(user).batchRegister(names, endpoints, { value: totalFee });
      const receipt = await tx.wait();

      // Check events
      const events = receipt.events.filter(e => e.event === "AgentRegistered");
      expect(events.length).to.equal(3);

      // Each agent should have correct owner and name in event
      for (let i = 0; i < 3; i++) {
        expect(events[i].args.owner).to.equal(user.address);
        expect(events[i].args.name).to.equal(names[i]);
      }

      // Verify agents are registered
      const ids = await tx.wait().then(r => {
        const evts = r.events.filter(e => e.event === "AgentRegistered");
        return evts.map(e => e.args.agentId);
      });

      for (const id of ids) {
        const agent = await registry.getAgent(id);
        expect(agent.owner).to.equal(user.address);
        expect(agent.active).to.equal(true);
        expect(agent.reputation).to.equal(100);
      }

      // Check owner agents list
      const ownerIds = await registry.ownerAgents(user.address, 0);
      expect(ownerIds).to.equal(ids[0]);
    });

    it("should register exactly 50 agents (max batch)", async function () {
      const names = Array.from({ length: 50 }, (_, i) => `Agent-${i}`);
      const endpoints = Array.from({ length: 50 }, (_, i) => `https://api${i}.com`);
      const totalFee = FEE.mul(50);

      const tx = await registry.connect(user).batchRegister(names, endpoints, { value: totalFee });
      const receipt = await tx.wait();
      expect(receipt.events.filter(e => e.event === "AgentRegistered").length).to.equal(50);
    });

    it("should register exactly 1 agent in a batch", async function () {
      const tx = await registry.connect(user).batchRegister(
        ["Solo-Agent"], ["https://solo.api"], { value: FEE }
      );
      const receipt = await tx.wait();
      expect(receipt.events.filter(e => e.event === "AgentRegistered").length).to.equal(1);
    });

    it("should collect total fee once", async function () {
      const balanceBefore = await ethers.provider.getBalance(registry.address);
      await registry.connect(user).batchRegister(
        ["A", "B", "C"], ["a", "b", "c"], { value: FEE.mul(3) }
      );
      const balanceAfter = await ethers.provider.getBalance(registry.address);
      expect(balanceAfter.sub(balanceBefore)).to.equal(FEE.mul(3));
    });

    it("should revert on array length mismatch", async function () {
      await expect(
        registry.connect(user).batchRegister(
          ["Agent1", "Agent2"], ["https://only-one.api"], { value: FEE.mul(2) }
        )
      ).to.be.revertedWith("Array length mismatch");
    });

    it("should revert on insufficient fee", async function () {
      await expect(
        registry.connect(user).batchRegister(
          ["A", "B"], ["a", "b"], { value: FEE.mul(1) }
        )
      ).to.be.revertedWith("Insufficient fee");
    });

    it("should revert on empty batch", async function () {
      await expect(
        registry.connect(user).batchRegister([], [], { value: 0 })
      ).to.be.revertedWith("Empty batch");
    });

    it("should revert on batch exceeding MAX_BATCH_SIZE", async function () {
      const names = Array.from({ length: 51 }, (_, i) => `Agent-${i}`);
      const endpoints = Array.from({ length: 51 }, (_, i) => `https://api${i}.com`);
      await expect(
        registry.connect(user).batchRegister(names, endpoints, { value: FEE.mul(51) })
      ).to.be.revertedWith("Batch too large");
    });

    it("should revert on invalid name in batch", async function () {
      await expect(
        registry.connect(user).batchRegister(
          ["A", ""], ["a", "b"], { value: FEE.mul(2) }
        )
      ).to.be.revertedWith("Invalid name");
    });

    it("should generate unique IDs for each agent in batch", async function () {
      const tx = await registry.connect(user).batchRegister(
        ["X", "Y", "Z"], ["x", "y", "z"], { value: FEE.mul(3) }
      );
      const receipt = await tx.wait();
      const ids = receipt.events
        .filter(e => e.event === "AgentRegistered")
        .map(e => e.args.agentId);
      
      // All IDs must be unique
      expect(new Set(ids.map(id => id.toString())).size).to.equal(3);
    });

    it("should return array of agent IDs", async function () {
      const result = await registry.connect(user).callStatic.batchRegister(
        ["A", "B"], ["a", "b"], { value: FEE.mul(2) }
      );
      expect(result.length).to.equal(2);
    });

    it("should work alongside single registerAgent", async function () {
      // Batch register
      await registry.connect(user).batchRegister(
        ["Batch1", "Batch2"], ["b1", "b2"], { value: FEE.mul(2) }
      );
      // Single register
      await registry.connect(user).registerAgent("Single", "single", { value: FEE });

      expect(await registry.getActiveAgentCount()).to.equal(3);
    });
  });
});
