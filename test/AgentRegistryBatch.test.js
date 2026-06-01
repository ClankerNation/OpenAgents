const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry — batchRegister", function () {
  let registry;
  let owner, user;

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners();
    const Registry = await ethers.getContractFactory("AgentRegistry");
    registry = await Registry.deploy(ethers.parseEther("0.01"));
    await registry.waitForDeployment();
  });

  it("batch of 1 agent", async function () {
    const fee = await registry.registrationFee();
    const tx = await registry.connect(user).batchRegister(
      ["agent-one"],
      ["https://agent1.example"],
      { value: fee }
    );
    const receipt = await tx.wait();

    // Check events
    const events = receipt.logs.filter(
      (log) => log.fragment && log.fragment.name === "AgentRegistered"
    );
    expect(events.length).to.equal(1);

    // Verify agent was registered
    const ids = await registry.connect(user).batchRegister.staticCall(
      ["test-check"],
      ["https://test.example"],
      { value: fee }
    );
    expect(ids.length).to.equal(1);
  });

  it("batch of 50 agents", async function () {
    const fee = await registry.registrationFee();
    const totalFee = fee * 50n;

    const names = Array.from({ length: 50 }, (_, i) => `agent-${i}`);
    const endpoints = Array.from({ length: 50 }, (_, i) => `https://agent${i}.example`);

    const tx = await registry.connect(user).batchRegister(
      names,
      endpoints,
      { value: totalFee }
    );
    const receipt = await tx.wait();

    const events = receipt.logs.filter(
      (log) => log.fragment && log.fragment.name === "AgentRegistered"
    );
    expect(events.length).to.equal(50);

    expect(await registry.getActiveAgentCount()).to.equal(50);
  });

  it("reverts on array length mismatch", async function () {
    const fee = await registry.registrationFee();
    await expect(
      registry.connect(user).batchRegister(
        ["agent-a", "agent-b"],
        ["https://one.example"],
        { value: fee * 2n }
      )
    ).to.be.revertedWith("Array length mismatch");
  });

  it("reverts when total fee is insufficient", async function () {
    const fee = await registry.registrationFee();
    await expect(
      registry.connect(user).batchRegister(
        ["agent-a", "agent-b", "agent-c"],
        ["https://a.example", "https://b.example", "https://c.example"],
        { value: fee } // only 1x fee for 3 registrations
      )
    ).to.be.revertedWith("Insufficient total fee");
  });

  it("reverts on batch size zero", async function () {
    await expect(
      registry.connect(user).batchRegister([], [])
    ).to.be.revertedWith("Batch size must be 1-50");
  });

  it("reverts on batch size exceeding 50", async function () {
    const names = Array.from({ length: 51 }, (_, i) => `agent-${i}`);
    const endpoints = Array.from({ length: 51 }, (_, i) => `https://agent${i}.example`);
    const fee = await registry.registrationFee();

    await expect(
      registry.connect(user).batchRegister(names, endpoints, { value: fee * 51n })
    ).to.be.revertedWith("Batch size must be 1-50");
  });
});
