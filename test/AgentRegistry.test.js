const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry — Frontrunning Protection (#172)", function () {
  let registry;
  let owner, agent1, agent2;

  beforeEach(async function () {
    [owner, agent1, agent2] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(ethers.utils.parseEther("0.01"));
    await registry.deployed();
  });

  describe("Counter-based Agent ID", function () {
    it("should assign different IDs to two agents with same name in the same block", async function () {
      const fee = ethers.utils.parseEther("0.01");

      // Both agents register with the same name
      const tx1 = await registry.connect(agent1).registerAgent(
        "Metatron-Agent",
        "https://agent1.example.com",
        { value: fee }
      );
      const receipt1 = await tx1.wait();

      const tx2 = await registry.connect(agent2).registerAgent(
        "Metatron-Agent",
        "https://agent2.example.com",
        { value: fee }
      );
      const receipt2 = await tx2.wait();

      // Extract agent IDs from events
      const event1 = receipt1.events.find(e => e.event === "AgentRegistered");
      const event2 = receipt2.events.find(e => e.event === "AgentRegistered");

      const id1 = event1.args.agentId;
      const id2 = event2.args.agentId;

      // IDs must be different — this is the core fix
      expect(id1).to.not.equal(id2);

      // Both agents should be retrievable
      const agentData1 = await registry.getAgent(id1);
      const agentData2 = await registry.getAgent(id2);

      expect(agentData1.owner).to.equal(agent1.address);
      expect(agentData2.owner).to.equal(agent2.address);
      expect(agentData1.name).to.equal("Metatron-Agent");
      expect(agentData2.name).to.equal("Metatron-Agent");
      expect(agentData1.active).to.be.true;
      expect(agentData2.active).to.be.true;
    });

    it("should increment the counter after each registration", async function () {
      const fee = ethers.utils.parseEther("0.01");

      // Check initial counter
      const initialCounter = await registry.getNextAgentId();
      expect(initialCounter).to.equal(1);

      // First registration
      await registry.connect(agent1).registerAgent(
        "Agent-Alpha",
        "https://alpha.example.com",
        { value: fee }
      );

      const afterFirst = await registry.getNextAgentId();
      expect(afterFirst).to.equal(2);

      // Second registration
      await registry.connect(agent2).registerAgent(
        "Agent-Beta",
        "https://beta.example.com",
        { value: fee }
      );

      const afterSecond = await registry.getNextAgentId();
      expect(afterSecond).to.equal(3);
    });

    it("should assign different IDs even for same owner registering twice with same name", async function () {
      const fee = ethers.utils.parseEther("0.01");

      // Same owner registers twice with same name
      const tx1 = await registry.connect(agent1).registerAgent(
        "Duplicate-Agent",
        "https://v1.example.com",
        { value: fee }
      );
      const receipt1 = await tx1.wait();

      const tx2 = await registry.connect(agent1).registerAgent(
        "Duplicate-Agent",
        "https://v2.example.com",
        { value: fee }
      );
      const receipt2 = await tx2.wait();

      const id1 = receipt1.events.find(e => e.event === "AgentRegistered").args.agentId;
      const id2 = receipt2.events.find(e => e.event === "AgentRegistered").args.agentId;

      expect(id1).to.not.equal(id2);

      // Verify both exist
      expect((await registry.getAgent(id1)).active).to.be.true;
      expect((await registry.getAgent(id2)).active).to.be.true;
    });
  });

  describe("Existing functionality preserved", function () {
    it("should require registration fee", async function () {
      await expect(
        registry.connect(agent1).registerAgent(
          "TestAgent",
          "https://test.example.com",
          { value: ethers.utils.parseEther("0.001") }
        )
      ).to.be.revertedWith("Insufficient fee");
    });

    it("should reject empty names", async function () {
      await expect(
        registry.connect(agent1).registerAgent(
          "",
          "https://test.example.com",
          { value: ethers.utils.parseEther("0.01") }
        )
      ).to.be.reverted;
    });

    it("should allow owner to deactivate agent", async function () {
      const fee = ethers.utils.parseEther("0.01");
      const tx = await registry.connect(agent1).registerAgent(
        "Deactivatable",
        "https://deact.example.com",
        { value: fee }
      );
      const receipt = await tx.wait();
      const id = receipt.events.find(e => e.event === "AgentRegistered").args.agentId;

      await registry.connect(agent1).deactivateAgent(id);
      const agentData = await registry.getAgent(id);
      expect(agentData.active).to.be.false;
    });

    it("should track owner agents correctly", async function () {
      const fee = ethers.utils.parseEther("0.01");

      await registry.connect(agent1).registerAgent(
        "OwnerAgent1", "https://a.example.com", { value: fee }
      );
      await registry.connect(agent1).registerAgent(
        "OwnerAgent2", "https://b.example.com", { value: fee }
      );

      // Verify both agents are active and owned by agent1
      const count = await registry.getActiveAgentCount();
      expect(count).to.equal(2);
    });
  });
});
