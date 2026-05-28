const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry - Batch Operations", function () {
  let agentRegistry;
  let owner, user1, user2;
  const REGISTRATION_FEE = ethers.parseEther("0.01");

  beforeEach(async function () {
    [owner, user1, user2] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    agentRegistry = await AgentRegistry.deploy(REGISTRATION_FEE);
    await agentRegistry.waitForDeployment();
  });

  // Helper to count registered agents by parsing events
  async function getAgentCount() {
    // agentIds is a public array, we can query it by index until it reverts
    let count = 0;
    try {
      for (let i = 0; i < 200; i++) {
        await agentRegistry.agentIds(i);
        count++;
      }
    } catch (e) {
      // Expected - array out of bounds
    }
    return count;
  }

  describe("Single registration (backward compatibility)", function () {
    it("should register a single agent", async function () {
      const tx = await agentRegistry.connect(user1).registerAgent("Agent1", "https://agent1.example.com", {
        value: REGISTRATION_FEE,
      });
      const receipt = await tx.wait();

      const events = receipt.logs.filter(
        (log) => { try { return agentRegistry.interface.parseLog(log)?.name === "AgentRegistered"; } catch { return false; } }
      );
      expect(events.length).to.equal(1);

      expect(await getAgentCount()).to.equal(1);
    });
  });

  describe("batchRegister", function () {
    it("should register a batch of 1 agent", async function () {
      const names = ["SoloAgent"];
      const endpoints = ["https://solo.example.com"];

      const tx = await agentRegistry.connect(user1).batchRegister(names, endpoints, {
        value: REGISTRATION_FEE,
      });
      const receipt = await tx.wait();

      const events = receipt.logs.filter(
        (log) => { try { return agentRegistry.interface.parseLog(log)?.name === "AgentRegistered"; } catch { return false; } }
      );
      expect(events.length).to.equal(1);

      expect(await getAgentCount()).to.equal(1);

      // Verify the agent data
      const agentId = await agentRegistry.agentIds(0);
      const agent = await agentRegistry.getAgent(agentId);
      expect(agent.name).to.equal("SoloAgent");
      expect(agent.endpoint).to.equal("https://solo.example.com");
      expect(agent.owner).to.equal(user1.address);
      expect(agent.active).to.be.true;
      expect(agent.reputation).to.equal(100);
    });

    it("should register a batch of 50 agents", async function () {
      const names = [];
      const endpoints = [];
      for (let i = 0; i < 50; i++) {
        names.push(`Agent${i}`);
        endpoints.push(`https://agent${i}.example.com`);
      }

      const totalFee = REGISTRATION_FEE * 50n;

      const tx = await agentRegistry.connect(user1).batchRegister(names, endpoints, {
        value: totalFee,
      });
      const receipt = await tx.wait();

      const events = receipt.logs.filter(
        (log) => { try { return agentRegistry.interface.parseLog(log)?.name === "AgentRegistered"; } catch { return false; } }
      );
      expect(events.length).to.equal(50);

      expect(await getAgentCount()).to.equal(50);

      // Verify a few agents
      for (let i = 0; i < 50; i++) {
        const agentId = await agentRegistry.agentIds(i);
        const agent = await agentRegistry.getAgent(agentId);
        expect(agent.name).to.equal(`Agent${i}`);
        expect(agent.endpoint).to.equal(`https://agent${i}.example.com`);
        expect(agent.owner).to.equal(user1.address);
        expect(agent.active).to.be.true;
      }
    });

    it("should revert on array length mismatch", async function () {
      const names = ["Agent1", "Agent2"];
      const endpoints = ["https://agent1.example.com"];

      await expect(
        agentRegistry.connect(user1).batchRegister(names, endpoints, {
          value: REGISTRATION_FEE * 2n,
        })
      ).to.be.revertedWith("Array length mismatch");
    });

    it("should revert on empty batch", async function () {
      await expect(
        agentRegistry.connect(user1).batchRegister([], [], {
          value: 0,
        })
      ).to.be.revertedWith("Empty batch");
    });

    it("should revert on batch exceeding MAX_BATCH_SIZE", async function () {
      const names = [];
      const endpoints = [];
      for (let i = 0; i < 51; i++) {
        names.push(`Agent${i}`);
        endpoints.push(`https://agent${i}.example.com`);
      }

      await expect(
        agentRegistry.connect(user1).batchRegister(names, endpoints, {
          value: REGISTRATION_FEE * 51n,
        })
      ).to.be.revertedWith("Batch too large");
    });

    it("should revert on insufficient fee", async function () {
      const names = ["Agent1", "Agent2"];
      const endpoints = ["https://agent1.example.com", "https://agent2.example.com"];

      await expect(
        agentRegistry.connect(user1).batchRegister(names, endpoints, {
          value: REGISTRATION_FEE,
        })
      ).to.be.revertedWith("Insufficient fee");
    });

    it("should collect total fee once", async function () {
      const names = ["Agent1", "Agent2", "Agent3"];
      const endpoints = ["https://a1.example.com", "https://a2.example.com", "https://a3.example.com"];
      const totalFee = REGISTRATION_FEE * 3n;

      const contractAddr = await agentRegistry.getAddress();
      const balanceBefore = await ethers.provider.getBalance(contractAddr);

      await agentRegistry.connect(user1).batchRegister(names, endpoints, {
        value: totalFee,
      });

      const balanceAfter = await ethers.provider.getBalance(contractAddr);
      expect(balanceAfter - balanceBefore).to.equal(totalFee);
    });

    it("should allow multiple users to batch register", async function () {
      await agentRegistry.connect(user1).batchRegister(["A1", "A2"], ["e1", "e2"], {
        value: REGISTRATION_FEE * 2n,
      });

      await agentRegistry.connect(user2).batchRegister(["B1", "B2", "B3"], ["e3", "e4", "e5"], {
        value: REGISTRATION_FEE * 3n,
      });

      expect(await getAgentCount()).to.equal(5);
    });

    it("should return correct agent IDs", async function () {
      const names = ["Agent1", "Agent2"];
      const endpoints = ["https://a1.example.com", "https://a2.example.com"];

      const tx = await agentRegistry.connect(user1).batchRegister(names, endpoints, {
        value: REGISTRATION_FEE * 2n,
      });
      const receipt = await tx.wait();

      const events = receipt.logs.filter(
        (log) => { try { return agentRegistry.interface.parseLog(log)?.name === "AgentRegistered"; } catch { return false; } }
      );

      const agentIds = events.map((e) => agentRegistry.interface.parseLog(e).args.agentId);
      expect(agentIds.length).to.equal(2);
      expect(agentIds[0]).to.not.equal(agentIds[1]);

      for (const id of agentIds) {
        const agent = await agentRegistry.getAgent(id);
        expect(agent.registeredAt).to.be.gt(0);
      }
    });
  });
});
