const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry - batchRegister", function () {
  let registry, owner, signer1, signer2;
  const REGISTRATION_FEE = ethers.parseEther("0.01");

  beforeEach(async function () {
    [owner, signer1, signer2] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(REGISTRATION_FEE);
    await registry.waitForDeployment();
  });

  it("should register a batch of 1 agent", async function () {
    const names = ["AgentOne"];
    const endpoints = ["https://agent-one.example.com"];
    const totalFee = REGISTRATION_FEE * BigInt(names.length);

    const tx = await registry.connect(signer1).batchRegister(names, endpoints, { value: totalFee });
    const receipt = await tx.wait();

    // Verify the event was emitted
    const events = await registry.queryFilter(
      registry.filters.AgentRegistered(),
      receipt.blockNumber,
      receipt.blockNumber
    );
    expect(events.length).to.equal(1);
    expect(events[0].args.owner).to.equal(signer1.address);
    expect(events[0].args.name).to.equal("AgentOne");

    // Verify agent exists via getActiveAgentCount
    const count = await registry.getActiveAgentCount();
    expect(count).to.equal(1n);
  });

  it("should register a batch of 50 agents", async function () {
    const names = [];
    const endpoints = [];
    for (let i = 0; i < 50; i++) {
      names.push(`Agent${i}`);
      endpoints.push(`https://agent${i}.example.com`);
    }
    const totalFee = REGISTRATION_FEE * BigInt(names.length);

    const tx = await registry.connect(signer2).batchRegister(names, endpoints, { value: totalFee });
    const receipt = await tx.wait();

    // Should emit 50 AgentRegistered events
    const events = await registry.queryFilter(registry.filters.AgentRegistered(), receipt.blockNumber, receipt.blockNumber);
    expect(events.length).to.equal(50);

    // Verify all event addresses match the sender
    for (const event of events) {
      expect(event.args.owner).to.equal(signer2.address);
    }

    const count = await registry.getActiveAgentCount();
    expect(count).to.equal(50n);
  });

  it("should revert on array length mismatch", async function () {
    const names = ["Agent1", "Agent2"];
    const endpoints = ["https://agent1.example.com"]; // only 1 endpoint for 2 names
    const totalFee = REGISTRATION_FEE * BigInt(names.length);

    await expect(
      registry.connect(signer1).batchRegister(names, endpoints, { value: totalFee })
    ).to.be.revertedWith("Array length mismatch");
  });

  it("should revert on batch of 0 (empty arrays)", async function () {
    await expect(
      registry.connect(signer1).batchRegister([], [], { value: 0 })
    ).to.be.revertedWith("Invalid batch size");
  });

  it("should revert on batch exceeding 50", async function () {
    const names = [];
    const endpoints = [];
    for (let i = 0; i < 51; i++) {
      names.push(`Agent${i}`);
      endpoints.push(`https://agent${i}.example.com`);
    }
    const totalFee = REGISTRATION_FEE * BigInt(names.length);

    await expect(
      registry.connect(signer1).batchRegister(names, endpoints, { value: totalFee })
    ).to.be.revertedWith("Invalid batch size");
  });

  it("should revert on insufficient fee", async function () {
    const names = ["Agent1", "Agent2"];
    const endpoints = ["https://agent1.example.com", "https://agent2.example.com"];
    const insufficientFee = REGISTRATION_FEE; // only paying for 1 agent, needs 2

    await expect(
      registry.connect(signer1).batchRegister(names, endpoints, { value: insufficientFee })
    ).to.be.revertedWith("Insufficient total fee");
  });

  it("should collect total fee once for the entire batch", async function () {
    const names = ["AgentFee1", "AgentFee2", "AgentFee3"];
    const endpoints = ["https://fee1.example.com", "https://fee2.example.com", "https://fee3.example.com"];
    const totalFee = REGISTRATION_FEE * BigInt(names.length);

    const balanceBefore = await ethers.provider.getBalance(registry.target);
    await registry.connect(signer1).batchRegister(names, endpoints, { value: totalFee });
    const balanceAfter = await ethers.provider.getBalance(registry.target);

    expect(balanceAfter - balanceBefore).to.equal(totalFee);
  });

  it("should revert on empty name in batch", async function () {
    const names = ["ValidName", ""];
    const endpoints = ["https://valid.example.com", "https://empty.example.com"];
    const totalFee = REGISTRATION_FEE * BigInt(names.length);

    await expect(
      registry.connect(signer1).batchRegister(names, endpoints, { value: totalFee })
    ).to.be.revertedWith("Invalid name at index");
  });

  it("should be backwards compatible (single registerAgent still works)", async function () {
    // Verify existing single registration still functions
    const tx = await registry.connect(signer1).registerAgent("SingleAgent", "https://single.example.com", {
      value: REGISTRATION_FEE
    });
    await expect(tx).to.emit(registry, "AgentRegistered");

    const count = await registry.getActiveAgentCount();
    expect(count).to.equal(1n);

    // Then use batch
    const names = ["BatchAgent"];
    const endpoints = ["https://batch.example.com"];
    await registry.connect(signer1).batchRegister(names, endpoints, { value: REGISTRATION_FEE });
    const countAfter = await registry.getActiveAgentCount();
    expect(countAfter).to.equal(2n);
  });
});
