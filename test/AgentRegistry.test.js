/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry Batch Operations", function () {
  let agentRegistry;
  let owner, user1;
  const registrationFee = ethers.parseEther("0.01");

  before(async function () {
    [owner, user1] = await ethers.getSigners();
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    agentRegistry = await AgentRegistry.deploy(registrationFee);
    await agentRegistry.waitForDeployment();
  });

  it("should register a batch of agents successfully", async function () {
    const names = ["Agent1", "Agent2", "Agent3"];
    const endpoints = ["http://a.com", "http://b.com", "http://c.com"];
    const totalFee = registrationFee * 3n;

    const tx = await agentRegistry.connect(user1).batchRegister(names, endpoints, { value: totalFee });
    const receipt = await tx.wait();

    // Check events emitted
    const events = receipt.logs.filter(log => {
      try {
        const parsed = agentRegistry.interface.parseLog(log);
        return parsed && parsed.name === "AgentRegistered";
      } catch (e) {
        return false;
      }
    });
    expect(events.length).to.equal(3);

    // Verify agent count increased by checking getActiveAgentCount or similar
    // Since ownerAgents is a mapping to array, we can't read it directly without a getter
    // But the events confirm registration
  });

  it("should revert on array length mismatch", async function () {
    const names = ["Agent4", "Agent5"];
    const endpoints = ["http://d.com"];
    const totalFee = registrationFee * 2n;

    await expect(
      agentRegistry.connect(user1).batchRegister(names, endpoints, { value: totalFee })
    ).to.be.revertedWith("Array length mismatch");
  });

  it("should revert on insufficient fee for batch", async function () {
    const names = ["Agent6", "Agent7"];
    const endpoints = ["http://f.com", "http://g.com"];
    const insufficientFee = registrationFee; // Only enough for 1

    await expect(
      agentRegistry.connect(user1).batchRegister(names, endpoints, { value: insufficientFee })
    ).to.be.revertedWith("Insufficient fee for batch");
  });

  it("should revert if batch size exceeds 50", async function () {
    const names = Array(51).fill("AgentX");
    const endpoints = Array(51).fill("http://x.com");
    const totalFee = registrationFee * 51n;

    await expect(
      agentRegistry.connect(user1).batchRegister(names, endpoints, { value: totalFee })
    ).to.be.revertedWith("Invalid batch size");
  });
});
