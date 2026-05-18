const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry", function () {
  let registry;
  let owner, user1, user2, nonOwner;
  const REGISTRATION_FEE = ethers.utils.parseEther("0.01");

  beforeEach(async function () {
    [owner, user1, user2, nonOwner] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(REGISTRATION_FEE);
    await registry.deployed();
  });

  describe("Single agent registration", function () {
    it("should register a single agent with correct fee", async function () {
      const tx = await registry.connect(user1).registerAgent("Agent1", "https://api.agent1.com", { value: REGISTRATION_FEE });
      const receipt = await tx.wait();

      expect(receipt.events).to.not.be.undefined;
      const regEvent = receipt.events.find(e => e.event === "AgentRegistered");
      expect(regEvent).to.not.be.undefined;
      expect(regEvent.args.owner).to.equal(user1.address);
      expect(regEvent.args.name).to.equal("Agent1");
    });

    it("should revert if fee is insufficient", async function () {
      await expect(
        registry.connect(user1).registerAgent("Agent1", "https://api.agent1.com", { value: 0 })
      ).to.be.revertedWith("Insufficient fee");
    });

    it("should revert if name is empty", async function () {
      await expect(
        registry.connect(user1).registerAgent("", "https://api.agent1.com", { value: REGISTRATION_FEE })
      ).to.be.revertedWith("Invalid name");
    });

    it("should revert if name is too long", async function () {
      const longName = "a".repeat(65);
      await expect(
        registry.connect(user1).registerAgent(longName, "https://api.agent1.com", { value: REGISTRATION_FEE })
      ).to.be.revertedWith("Invalid name");
    });
  });

  describe("batchRegister", function () {
    it("should register a batch of 1 agent", async function () {
      const names = ["BatchAgent1"];
      const endpoints = ["https://batch1.com"];
      const totalFee = REGISTRATION_FEE.mul(1);

      const tx = await registry.connect(user1).batchRegister(names, endpoints, { value: totalFee });
      const receipt = await tx.wait();

      const regEvents = receipt.events.filter(e => e.event === "AgentRegistered");
      expect(regEvents.length).to.equal(1);
      expect(regEvents[0].args.owner).to.equal(user1.address);
      expect(regEvents[0].args.name).to.equal("BatchAgent1");

      // Check agent is stored
      const agentId = regEvents[0].args.agentId;
      const agent = await registry.getAgent(agentId);
      expect(agent.owner).to.equal(user1.address);
      expect(agent.name).to.equal("BatchAgent1");
      expect(agent.endpoint).to.equal("https://batch1.com");
      expect(agent.active).to.be.true;
    });

    it("should register a batch of 50 agents", async function () {
      const count = 50;
      const names = [];
      const endpoints = [];
      for (let i = 0; i < count; i++) {
        names.push(`BatchAgent${i}`);
        endpoints.push(`https://batch${i}.com`);
      }
      const totalFee = REGISTRATION_FEE.mul(count);

      const tx = await registry.connect(user1).batchRegister(names, endpoints, { value: totalFee });
      const receipt = await tx.wait();

      const regEvents = receipt.events.filter(e => e.event === "AgentRegistered");
      expect(regEvents.length).to.equal(50);

      // Verify all agents are stored
      for (let i = 0; i < count; i++) {
        const agentId = regEvents[i].args.agentId;
        const agent = await registry.getAgent(agentId);
        expect(agent.owner).to.equal(user1.address);
        expect(agent.name).to.equal(`BatchAgent${i}`);
        expect(agent.endpoint).to.equal(`https://batch${i}.com`);
        expect(agent.active).to.be.true;
      }
    });

    it("should revert on array length mismatch", async function () {
      const names = ["Agent1", "Agent2"];
      const endpoints = ["https://1.com"]; // only 1 endpoint for 2 names
      const totalFee = REGISTRATION_FEE.mul(2);

      await expect(
        registry.connect(user1).batchRegister(names, endpoints, { value: totalFee })
      ).to.be.revertedWith("Array length mismatch");
    });

    it("should revert if batch size is 0 (empty arrays)", async function () {
      await expect(
        registry.connect(user1).batchRegister([], [], { value: 0 })
      ).to.be.revertedWith("Batch size out of range");
    });

    it("should revert if batch size exceeds MAX_BATCH_SIZE (51)", async function () {
      const names = [];
      const endpoints = [];
      for (let i = 0; i < 51; i++) {
        names.push(`Agent${i}`);
        endpoints.push(`https://${i}.com`);
      }
      const totalFee = REGISTRATION_FEE.mul(51);

      await expect(
        registry.connect(user1).batchRegister(names, endpoints, { value: totalFee })
      ).to.be.revertedWith("Batch size out of range");
    });

    it("should revert if total fee is insufficient", async function () {
      const names = ["Agent1", "Agent2"];
      const endpoints = ["https://1.com", "https://2.com"];
      // Sending fee for only 1 agent instead of 2
      const insufficientFee = REGISTRATION_FEE.mul(1);

      await expect(
        registry.connect(user1).batchRegister(names, endpoints, { value: insufficientFee })
      ).to.be.revertedWith("Insufficient fee");
    });

    it("should revert if any name in the batch is empty", async function () {
      const names = ["ValidName", ""];
      const endpoints = ["https://1.com", "https://2.com"];
      const totalFee = REGISTRATION_FEE.mul(2);

      await expect(
        registry.connect(user1).batchRegister(names, endpoints, { value: totalFee })
      ).to.be.revertedWith("Invalid name");
    });

    it("should revert if any name in the batch is too long", async function () {
      const names = ["ValidName", "a".repeat(65)];
      const endpoints = ["https://1.com", "https://2.com"];
      const totalFee = REGISTRATION_FEE.mul(2);

      await expect(
        registry.connect(user1).batchRegister(names, endpoints, { value: totalFee })
      ).to.be.revertedWith("Invalid name");
    });

    it("should calculate total fee as registrationFee * count", async function () {
      const count = 3;
      const names = ["A1", "A2", "A3"];
      const endpoints = ["https://1.com", "https://2.com", "https://3.com"];
      const exactFee = REGISTRATION_FEE.mul(count);

      // Should succeed with exact fee
      await expect(
        registry.connect(user1).batchRegister(names, endpoints, { value: exactFee })
      ).to.not.be.reverted;

      // Should fail with slightly less
      const insufficientFee = exactFee.sub(1);
      await expect(
        registry.connect(user2).batchRegister(names, endpoints, { value: insufficientFee })
      ).to.be.revertedWith("Insufficient fee");
    });

    it("should give each agent a unique ID", async function () {
      const names = ["Unique1", "Unique2", "Unique3"];
      const endpoints = ["https://1.com", "https://2.com", "https://3.com"];
      const totalFee = REGISTRATION_FEE.mul(3);

      const tx = await registry.connect(user1).batchRegister(names, endpoints, { value: totalFee });
      const receipt = await tx.wait();

      const regEvents = receipt.events.filter(e => e.event === "AgentRegistered");
      const ids = regEvents.map(e => e.args.agentId);

      // All IDs should be unique
      const uniqueIds = new Set(ids.map(id => id));
      expect(uniqueIds.size).to.equal(3);
    });
  });

  describe("batchUpdate", function () {
    async function registerAgents(user, names, endpoints) {
      const totalFee = REGISTRATION_FEE.mul(names.length);
      const tx = await registry.connect(user).batchRegister(names, endpoints, { value: totalFee });
      const receipt = await tx.wait();
      return receipt.events.filter(e => e.event === "AgentRegistered").map(e => e.args.agentId);
    }

    it("should update multiple agent endpoints", async function () {
      const names = ["UpdAgent1", "UpdAgent2"];
      const endpoints = ["https://old1.com", "https://old2.com"];
      const agentIds = await registerAgents(user1, names, endpoints);

      const newEndpoints = ["https://new1.com", "https://new2.com"];
      const tx = await registry.connect(user1).batchUpdate(agentIds, newEndpoints);
      const receipt = await tx.wait();

      const updateEvents = receipt.events.filter(e => e.event === "AgentMetadataUpdated");
      expect(updateEvents.length).to.equal(2);

      // Verify endpoints updated
      for (let i = 0; i < agentIds.length; i++) {
        const agent = await registry.getAgent(agentIds[i]);
        expect(agent.endpoint).to.equal(newEndpoints[i]);
      }
    });

    it("should revert on array length mismatch", async function () {
      const names = ["UpdAgent1", "UpdAgent2"];
      const endpoints = ["https://1.com", "https://2.com"];
      const agentIds = await registerAgents(user1, names, endpoints);

      await expect(
        registry.connect(user1).batchUpdate([agentIds[0]], ["https://new.com", "https://extra.com"])
      ).to.be.revertedWith("Array length mismatch");
    });

    it("should revert if caller is not agent owner", async function () {
      const names = ["OwnerAgent1"];
      const endpoints = ["https://1.com"];
      const agentIds = await registerAgents(user1, names, endpoints);

      await expect(
        registry.connect(nonOwner).batchUpdate(agentIds, ["https://hacked.com"])
      ).to.be.revertedWith("Not agent owner");
    });

    it("should revert if agent is not active (deactivated)", async function () {
      const names = ["DeactAgent1"];
      const endpoints = ["https://1.com"];
      const agentIds = await registerAgents(user1, names, endpoints);

      // Deactivate the agent
      await registry.connect(user1).deactivateAgent(agentIds[0]);

      await expect(
        registry.connect(user1).batchUpdate(agentIds, ["https://updated.com"])
      ).to.be.revertedWith("Agent not active");
    });

    it("should revert on empty batch (size 0)", async function () {
      await expect(
        registry.connect(user1).batchUpdate([], [])
      ).to.be.revertedWith("Batch size out of range");
    });

    it("should revert on batch size exceeding MAX_BATCH_SIZE", async function () {
      const agentIds = new Array(51).fill(ethers.constants.HashZero);
      const endpoints = new Array(51).fill("https://x.com");

      await expect(
        registry.connect(user1).batchUpdate(agentIds, endpoints)
      ).to.be.revertedWith("Batch size out of range");
    });
  });

  describe("batchDeregister", function () {
    async function registerAgents(user, names, endpoints) {
      const totalFee = REGISTRATION_FEE.mul(names.length);
      const tx = await registry.connect(user).batchRegister(names, endpoints, { value: totalFee });
      const receipt = await tx.wait();
      return receipt.events.filter(e => e.event === "AgentRegistered").map(e => e.args.agentId);
    }

    it("should deactivate multiple agents", async function () {
      const names = ["DerAgent1", "DerAgent2", "DerAgent3"];
      const endpoints = ["https://1.com", "https://2.com", "https://3.com"];
      const agentIds = await registerAgents(user1, names, endpoints);

      const tx = await registry.connect(user1).batchDeregister(agentIds);
      const receipt = await tx.wait();

      const deactEvents = receipt.events.filter(e => e.event === "AgentDeactivated");
      expect(deactEvents.length).to.equal(3);

      // Verify all agents deactivated
      for (const aid of agentIds) {
        const agent = await registry.getAgent(aid);
        expect(agent.active).to.be.false;
      }
    });

    it("should revert if caller is not agent owner", async function () {
      const names = ["DerOwner1"];
      const endpoints = ["https://1.com"];
      const agentIds = await registerAgents(user1, names, endpoints);

      await expect(
        registry.connect(nonOwner).batchDeregister(agentIds)
      ).to.be.revertedWith("Not agent owner");
    });

    it("should revert if agent is already deactivated", async function () {
      const names = ["DerDeact1"];
      const endpoints = ["https://1.com"];
      const agentIds = await registerAgents(user1, names, endpoints);

      // First deregister - should succeed
      await registry.connect(user1).batchDeregister(agentIds);

      // Second deregister - should fail (agent not active)
      await expect(
        registry.connect(user1).batchDeregister(agentIds)
      ).to.be.revertedWith("Agent not active");
    });

    it("should revert on empty batch (size 0)", async function () {
      await expect(
        registry.connect(user1).batchDeregister([])
      ).to.be.revertedWith("Batch size out of range");
    });

    it("should revert on batch size exceeding MAX_BATCH_SIZE", async function () {
      const agentIds = new Array(51).fill(ethers.constants.HashZero);

      await expect(
        registry.connect(user1).batchDeregister(agentIds)
      ).to.be.revertedWith("Batch size out of range");
    });

    it("should emit AgentDeactivated event for each agent", async function () {
      const names = ["EvAgent1", "EvAgent2"];
      const endpoints = ["https://1.com", "https://2.com"];
      const agentIds = await registerAgents(user1, names, endpoints);

      const tx = await registry.connect(user1).batchDeregister(agentIds);
      const receipt = await tx.wait();

      const deactEvents = receipt.events.filter(e => e.event === "AgentDeactivated");
      expect(deactEvents.length).to.equal(2);

      // Verify event order matches input order
      for (let i = 0; i < agentIds.length; i++) {
        expect(deactEvents[i].args.agentId).to.equal(agentIds[i]);
      }
    });
  });

  describe("Gas efficiency", function () {
    it("batchRegister should be cheaper than individual registrations", async function () {
      const count = 5;

      // Individual registrations
      let individualGas = ethers.BigNumber.from(0);
      for (let i = 0; i < count; i++) {
        const tx = await registry.connect(user1).registerAgent(`IndAgent${i}`, `https://ind${i}.com`, { value: REGISTRATION_FEE });
        const receipt = await tx.wait();
        individualGas = individualGas.add(receipt.gasUsed);
      }

      // Batch registration
      const names = [];
      const endpoints = [];
      for (let i = 0; i < count; i++) {
        names.push(`BatchAgent${i}`);
        endpoints.push(`https://batch${i}.com`);
      }
      const batchTx = await registry.connect(user2).batchRegister(names, endpoints, { value: REGISTRATION_FEE.mul(count) });
      const batchReceipt = await batchTx.wait();

      // Batch should use less gas total than individual transactions
      expect(batchReceipt.gasUsed.toNumber()).to.be.lessThan(individualGas.toNumber());
    });
  });

  describe("MAX_BATCH_SIZE constant", function () {
    it("should expose MAX_BATCH_SIZE as 50", async function () {
      expect(await registry.MAX_BATCH_SIZE()).to.equal(50);
    });
  });
});
