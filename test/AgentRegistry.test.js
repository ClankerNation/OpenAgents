const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry", function () {
  let registry;
  let owner, user1;
  const FEE = ethers.parseEther("0.01");

  beforeEach(async function () {
    [owner, user1] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("AgentRegistry");
    registry = await Factory.deploy(FEE);
    await registry.waitForDeployment();
  });

  it("should register a single agent via batchRegister", async function () {
    const names = ["Agent1"];
    const endpoints = ["https://agent1.example.com"];
    const fee = FEE * 1n;

    await expect(registry.connect(user1).batchRegister(names, endpoints, { value: fee }))
      .to.emit(registry, "AgentRegistered");

    // Verify via getAgent using the event or by checking agentIds length
    const count = await registry.getActiveAgentCount();
    expect(count).to.equal(1);
  });

  it("should register 50 agents in one transaction", async function () {
    const count = 50;
    const names = [];
    const endpoints = [];
    for (let i = 0; i < count; i++) {
      names.push(`Agent${i}`);
      endpoints.push(`https://agent${i}.example.com`);
    }
    const fee = FEE * BigInt(count);

    const tx = await registry.connect(user1).batchRegister(names, endpoints, { value: fee });
    const receipt = await tx.wait();

    // Count AgentRegistered events
    const events = receipt.logs.filter(log => {
      try {
        return registry.interface.parseLog(log)?.name === "AgentRegistered";
      } catch { return false; }
    });
    expect(events.length).to.equal(count);

    const activeCount = await registry.getActiveAgentCount();
    expect(activeCount).to.equal(count);
  });

  it("should revert on array length mismatch", async function () {
    const names = ["Agent1", "Agent2"];
    const endpoints = ["https://agent1.example.com"];
    const fee = FEE * 2n;

    await expect(
      registry.connect(user1).batchRegister(names, endpoints, { value: fee })
    ).to.be.revertedWith("Array length mismatch");
  });

  it("should revert when insufficient fee paid", async function () {
    const names = ["Agent1", "Agent2"];
    const endpoints = ["https://a1.com", "https://a2.com"];
    const fee = FEE * 1n;

    await expect(
      registry.connect(user1).batchRegister(names, endpoints, { value: fee })
    ).to.be.revertedWith("Insufficient total fee");
  });

  it("should revert when batch size exceeds 50", async function () {
    const names = [];
    const endpoints = [];
    for (let i = 0; i < 51; i++) {
      names.push(`A${i}`);
      endpoints.push(`https://a${i}.com`);
    }
    const fee = FEE * 51n;

    await expect(
      registry.connect(user1).batchRegister(names, endpoints, { value: fee })
    ).to.be.revertedWith("Batch size must be 1-50");
  });
});
