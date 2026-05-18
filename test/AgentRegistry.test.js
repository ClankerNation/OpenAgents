const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry", function () {
  let registry;
  let owner, alice, bob;

  beforeEach(async function () {
    [owner, alice, bob] = await ethers.getSigners();
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(ethers.parseEther("0.01"));
    await registry.waitForDeployment();
  });

  describe("registerAgent", function () {
    it("should register an agent with a unique counter-based ID", async function () {
      const fee = ethers.parseEther("0.01");
      const tx = await registry.connect(alice).registerAgent("AliceBot", "https://alice.example.com", { value: fee });
      const receipt = await tx.wait();

      // First agent should get ID 1 (bytes32)
      const expectedId = ethers.zeroPadValue("0x01", 32);
      const agent = await registry.getAgent(expectedId);
      expect(agent.owner).to.equal(alice.address);
      expect(agent.name).to.equal("AliceBot");
      expect(agent.active).to.equal(true);
      expect(agent.reputation).to.equal(100n);
    });

    it("should assign sequential IDs to multiple registrations", async function () {
      const fee = ethers.parseEther("0.01");

      await registry.connect(alice).registerAgent("AliceBot", "https://alice.example.com", { value: fee });
      await registry.connect(bob).registerAgent("BobBot", "https://bob.example.com", { value: fee });

      const id1 = ethers.zeroPadValue("0x01", 32);
      const id2 = ethers.zeroPadValue("0x02", 32);

      const agent1 = await registry.getAgent(id1);
      const agent2 = await registry.getAgent(id2);

      expect(agent1.owner).to.equal(alice.address);
      expect(agent2.owner).to.equal(bob.address);
    });

    it("should prevent frontrunning — two agents with same name get different IDs", async function () {
      const fee = ethers.parseEther("0.01");

      // Both Alice and Bob try to register the SAME name
      // With counter-based IDs, both succeed with different IDs
      const tx1 = await registry.connect(alice).registerAgent("MyAgent", "https://alice.example.com", { value: fee });
      const tx2 = await registry.connect(bob).registerAgent("MyAgent", "https://bob.example.com", { value: fee });

      const receipt1 = await tx1.wait();
      const receipt2 = await tx2.wait();

      // Extract the two agent IDs from events
      const filter = registry.filters.AgentRegistered();
      const events = await registry.queryFilter(filter);

      expect(events.length).to.equal(2);

      const id1 = events[0].args.agentId;
      const id2 = events[1].args.agentId;

      // IDs must be different
      expect(id1).to.not.equal(id2);

      // Both agents should be registered and active
      const agent1 = await registry.getAgent(id1);
      const agent2 = await registry.getAgent(id2);

      expect(agent1.active).to.equal(true);
      expect(agent2.active).to.equal(true);
      expect(agent1.name).to.equal("MyAgent");
      expect(agent2.name).to.equal("MyAgent");
    });

    it("should register multiple agents from the same owner with unique IDs", async function () {
      const fee = ethers.parseEther("0.01");

      await registry.connect(alice).registerAgent("Agent1", "https://ep1.example.com", { value: fee });
      await registry.connect(alice).registerAgent("Agent2", "https://ep2.example.com", { value: fee });
      await registry.connect(alice).registerAgent("Agent3", "https://ep3.example.com", { value: fee });

      const id1 = ethers.zeroPadValue("0x01", 32);
      const id2 = ethers.zeroPadValue("0x02", 32);
      const id3 = ethers.zeroPadValue("0x03", 32);

      expect((await registry.getAgent(id1)).name).to.equal("Agent1");
      expect((await registry.getAgent(id2)).name).to.equal("Agent2");
      expect((await registry.getAgent(id3)).name).to.equal("Agent3");
    });

    it("should revert if fee is insufficient", async function () {
      const lowFee = ethers.parseEther("0.005");
      await expect(
        registry.connect(alice).registerAgent("CheapBot", "https://cheap.example.com", { value: lowFee })
      ).to.be.revertedWith("Insufficient fee");
    });

    it("should revert if name is empty", async function () {
      const fee = ethers.parseEther("0.01");
      await expect(
        registry.connect(alice).registerAgent("", "https://empty.example.com", { value: fee })
      ).to.be.revertedWith("Invalid name");
    });

    it("should revert if name exceeds 64 bytes", async function () {
      const fee = ethers.parseEther("0.01");
      const longName = "A".repeat(65);
      await expect(
        registry.connect(alice).registerAgent(longName, "https://long.example.com", { value: fee })
      ).to.be.reverted;
    });
  });

  describe("deactivateAgent", function () {
    it("should deactivate the agent and emit event", async function () {
      const fee = ethers.parseEther("0.01");
      await registry.connect(alice).registerAgent("AliceBot", "https://alice.example.com", { value: fee });

      const agentId = ethers.zeroPadValue("0x01", 32);
      await expect(registry.connect(alice).deactivateAgent(agentId))
        .to.emit(registry, "AgentDeactivated")
        .withArgs(agentId);

      const agent = await registry.getAgent(agentId);
      expect(agent.active).to.equal(false);
    });

    it("should revert when non-owner tries to deactivate", async function () {
      const fee = ethers.parseEther("0.01");
      await registry.connect(alice).registerAgent("AliceBot", "https://alice.example.com", { value: fee });

      const agentId = ethers.zeroPadValue("0x01", 32);
      await expect(
        registry.connect(bob).deactivateAgent(agentId)
      ).to.be.revertedWith("Not agent owner");
    });
  });

  describe("updateReputation", function () {
    it("should update reputation as owner", async function () {
      const fee = ethers.parseEther("0.01");
      await registry.connect(alice).registerAgent("AliceBot", "https://alice.example.com", { value: fee });

      const agentId = ethers.zeroPadValue("0x01", 32);
      await registry.updateReputation(agentId, 50);

      const agent = await registry.getAgent(agentId);
      expect(agent.reputation).to.equal(150n);
    });

    it("should not reduce reputation below zero", async function () {
      const fee = ethers.parseEther("0.01");
      await registry.connect(alice).registerAgent("AliceBot", "https://alice.example.com", { value: fee });

      const agentId = ethers.zeroPadValue("0x01", 32);
      // Initial reputation is 100, decreasing by 200 should floor at 0
      await registry.updateReputation(agentId, -200);

      const agent = await registry.getAgent(agentId);
      expect(agent.reputation).to.equal(0n);
    });
  });

  describe("nextAgentId", function () {
    it("should return the next ID that will be assigned", async function () {
      expect(await registry.nextAgentId()).to.equal(1n);

      const fee = ethers.parseEther("0.01");
      await registry.connect(alice).registerAgent("Agent1", "https://ep1.example.com", { value: fee });
      expect(await registry.nextAgentId()).to.equal(2n);

      await registry.connect(bob).registerAgent("Agent2", "https://ep2.example.com", { value: fee });
      expect(await registry.nextAgentId()).to.equal(3n);
    });
  });
});
