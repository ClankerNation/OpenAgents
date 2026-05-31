const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry batchRegister", function () {
  let registry;
  let owner;
  let user;
  const registrationFee = ethers.parseEther("0.01");

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners();
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(registrationFee);
    await registry.waitForDeployment();
  });

  it("keeps registerAgent behavior (backwards compatibility)", async function () {
    const tx = await registry
      .connect(user)
      .registerAgent("single-agent", "https://single.example", { value: registrationFee });
    const receipt = await tx.wait();

    const events = await registry.queryFilter(
      registry.filters.AgentRegistered(),
      receipt.blockNumber,
      receipt.blockNumber
    );
    expect(events.length).to.equal(1);

    const agentId = events[0].args.agentId;
    const agent = await registry.getAgent(agentId);
    expect(agent.owner).to.equal(user.address);
    expect(agent.name).to.equal("single-agent");
    expect(agent.endpoint).to.equal("https://single.example");
    expect(agent.active).to.equal(true);
  });

  it("registers a batch of 1", async function () {
    const names = ["agent-1"];
    const endpoints = ["https://a1.example"];
    const tx = await registry.connect(user).batchRegister(names, endpoints, {
      value: registrationFee,
    });
    const receipt = await tx.wait();

    const events = await registry.queryFilter(
      registry.filters.AgentRegistered(),
      receipt.blockNumber,
      receipt.blockNumber
    );
    expect(events.length).to.equal(1);

    const agentId = events[0].args.agentId;
    const agent = await registry.getAgent(agentId);
    expect(agent.owner).to.equal(user.address);
    expect(agent.name).to.equal("agent-1");
  });

  it("registers a batch of 50 with unique ids", async function () {
    const names = [];
    const endpoints = [];
    for (let i = 0; i < 50; i++) {
      names.push(`agent-${i}`);
      endpoints.push(`https://agent-${i}.example`);
    }

    const tx = await registry.connect(user).batchRegister(names, endpoints, {
      value: registrationFee * 50n,
    });
    const receipt = await tx.wait();

    const events = await registry.queryFilter(
      registry.filters.AgentRegistered(),
      receipt.blockNumber,
      receipt.blockNumber
    );
    expect(events.length).to.equal(50);

    const ids = events.map((e) => e.args.agentId.toString());
    expect(new Set(ids).size).to.equal(50);

    const activeCount = await registry.getActiveAgentCount();
    expect(activeCount).to.equal(50n);
  });

  it("reverts when names and endpoints lengths mismatch", async function () {
    await expect(
      registry.connect(user).batchRegister(["a", "b"], ["https://a.example"], {
        value: registrationFee * 2n,
      })
    ).to.be.revertedWith("Array length mismatch");
  });

  it("collects total fee once for the whole batch", async function () {
    const balanceBefore = await ethers.provider.getBalance(await registry.getAddress());
    await registry.connect(user).batchRegister(
      ["a", "b", "c"],
      ["https://a.example", "https://b.example", "https://c.example"],
      { value: registrationFee * 3n }
    );
    const balanceAfter = await ethers.provider.getBalance(await registry.getAddress());
    expect(balanceAfter - balanceBefore).to.equal(registrationFee * 3n);
  });
});
