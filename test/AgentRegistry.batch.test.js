const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry Batch Operations", function () {
  let agentRegistry;
  let owner, user;

  const REGISTRATION_FEE = ethers.parseEther("0.01");
  const BATCH_50_FEE = REGISTRATION_FEE * 50n;

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    agentRegistry = await AgentRegistry.deploy(REGISTRATION_FEE);
    await agentRegistry.waitForDeployment();
  });

  describe("batchRegister", function () {
    it("should register a single agent via batch (batch of 1)", async function () {
      const names = ["AgentOne"];
      const endpoints = ["https://agent1.example.com"];

      const tx = await agentRegistry.connect(user).batchRegister(names, endpoints, {
        value: REGISTRATION_FEE,
      });

      const receipt = await tx.wait();

      // Check events
      const events = receipt.logs
        .map((log) => {
          try {
            return agentRegistry.interface.parseLog({ topics: log.topics, data: log.data });
          } catch {
            return null;
          }
        })
        .filter(Boolean);

      const registeredEvents = events.filter((e) => e.name === "AgentRegistered");
      expect(registeredEvents.length).to.equal(1);
      expect(registeredEvents[0].args.name).to.equal("AgentOne");
      expect(registeredEvents[0].args.owner).to.equal(user.address);

      // Verify agent was created
      const agentId = registeredEvents[0].args.agentId;
      const agent = await agentRegistry.getAgent(agentId);
      expect(agent.name).to.equal("AgentOne");
      expect(agent.endpoint).to.equal("https://agent1.example.com");
      expect(agent.owner).to.equal(user.address);
      expect(agent.active).to.be.true;
      expect(agent.reputation).to.equal(100);
    });

    it("should register 50 agents in a single transaction (batch of 50)", async function () {
      const names = [];
      const endpoints = [];
      for (let i = 0; i < 50; i++) {
        names.push(`Agent${i}`);
        endpoints.push(`https://agent${i}.example.com`);
      }

      const tx = await agentRegistry.connect(user).batchRegister(names, endpoints, {
        value: BATCH_50_FEE,
      });

      const receipt = await tx.wait();

      // Parse all AgentRegistered events
      const events = receipt.logs
        .map((log) => {
          try {
            return agentRegistry.interface.parseLog({ topics: log.topics, data: log.data });
          } catch {
            return null;
          }
        })
        .filter(Boolean);

      const registeredEvents = events.filter((e) => e.name === "AgentRegistered");
      expect(registeredEvents.length).to.equal(50);

      // Verify each agent has unique ID and correct data
      const seenIds = new Set();
      for (let i = 0; i < 50; i++) {
        const agentId = registeredEvents[i].args.agentId;
        expect(seenIds.has(agentId)).to.be.false;
        seenIds.add(agentId);

        const agent = await agentRegistry.getAgent(agentId);
        expect(agent.name).to.equal(`Agent${i}`);
        expect(agent.endpoint).to.equal(`https://agent${i}.example.com`);
        expect(agent.owner).to.equal(user.address);
        expect(agent.active).to.be.true;
        expect(agent.reputation).to.equal(100);
      }
    });

    it("should revert when array lengths mismatch", async function () {
      const names = ["AgentOne", "AgentTwo"];
      const endpoints = ["https://agent1.example.com"]; // Only one endpoint

      await expect(
        agentRegistry.connect(user).batchRegister(names, endpoints, {
          value: REGISTRATION_FEE * 2n,
        })
      ).to.be.revertedWith("Array length mismatch");
    });

    it("should revert when batch size exceeds maximum (51)", async function () {
      const names = [];
      const endpoints = [];
      for (let i = 0; i < 51; i++) {
        names.push(`Agent${i}`);
        endpoints.push(`https://agent${i}.example.com`);
      }

      await expect(
        agentRegistry.connect(user).batchRegister(names, endpoints, {
          value: REGISTRATION_FEE * 51n,
        })
      ).to.be.revertedWith("Batch too large");
    });

    it("should revert when batch is empty", async function () {
      await expect(
        agentRegistry.connect(user).batchRegister([], [], {
          value: 0,
        })
      ).to.be.revertedWith("Empty batch");
    });

    it("should revert when insufficient fee is sent", async function () {
      const names = ["AgentOne", "AgentTwo"];
      const endpoints = ["https://agent1.example.com", "https://agent2.example.com"];

      await expect(
        agentRegistry.connect(user).batchRegister(names, endpoints, {
          value: REGISTRATION_FEE, // Only 1 fee, but 2 agents
        })
      ).to.be.revertedWith("Insufficient fee");
    });

    it("should revert when a name exceeds 64 bytes", async function () {
      const longName = "A".repeat(65);
      const names = [longName];
      const endpoints = ["https://agent.example.com"];

      await expect(
        agentRegistry.connect(user).batchRegister(names, endpoints, {
          value: REGISTRATION_FEE,
        })
      ).to.be.revertedWith("Invalid name");
    });

    it("should revert when a name is empty", async function () {
      const names = [""];
      const endpoints = ["https://agent.example.com"];

      await expect(
        agentRegistry.connect(user).batchRegister(names, endpoints, {
          value: REGISTRATION_FEE,
        })
      ).to.be.revertedWith("Invalid name");
    });

    it("should return correct agent IDs array", async function () {
      const names = ["Alpha", "Beta", "Gamma"];
      const endpoints = ["a.com", "b.com", "c.com"];

      const ids = await agentRegistry.connect(user).batchRegister.staticCall(names, endpoints, {
        value: REGISTRATION_FEE * 3n,
      });

      expect(ids.length).to.equal(3);

      // Actually execute
      const tx = await agentRegistry.connect(user).batchRegister(names, endpoints, {
        value: REGISTRATION_FEE * 3n,
      });
      const receipt = await tx.wait();

      // Verify the returned IDs match the registered agents
      for (let i = 0; i < 3; i++) {
        const agent = await agentRegistry.getAgent(ids[i]);
        expect(agent.name).to.equal(names[i]);
      }
    });

    it("should accumulate total fees correctly (batch of 3)", async function () {
      const names = ["X", "Y", "Z"];
      const endpoints = ["x.com", "y.com", "z.com"];

      await agentRegistry.connect(user).batchRegister(names, endpoints, {
        value: REGISTRATION_FEE * 3n,
      });

      const balance = await ethers.provider.getBalance(await agentRegistry.getAddress());
      expect(balance).to.equal(REGISTRATION_FEE * 3n);
    });
  });

  describe("backwards compatibility", function () {
    it("should still allow single registerAgent after batchRegister", async function () {
      // Batch register first
      await agentRegistry.connect(user).batchRegister(
        ["BatchAgent"],
        ["https://batch.example.com"],
        { value: REGISTRATION_FEE }
      );

      // Then single register
      const tx = await agentRegistry.connect(user).registerAgent(
        "SingleAgent",
        "https://single.example.com",
        { value: REGISTRATION_FEE }
      );

      const receipt = await tx.wait();
      const events = receipt.logs
        .map((log) => {
          try {
            return agentRegistry.interface.parseLog({ topics: log.topics, data: log.data });
          } catch {
            return null;
          }
        })
        .filter(Boolean);

      const registeredEvents = events.filter((e) => e.name === "AgentRegistered");
      expect(registeredEvents.length).to.equal(1);
      expect(registeredEvents[0].args.name).to.equal("SingleAgent");
    });

    it("should maintain separate owner agent lists", async function () {
      const [owner, user2] = await ethers.getSigners();

      await agentRegistry.connect(user).batchRegister(
        ["User1Agent"],
        ["https://u1.example.com"],
        { value: REGISTRATION_FEE }
      );

      await agentRegistry.connect(user2).registerAgent(
        "User2Agent",
        "https://u2.example.com",
        { value: REGISTRATION_FEE }
      );

      // getActiveAgentCount should reflect both
      expect(await agentRegistry.getActiveAgentCount()).to.equal(2);
    });
  });
});
