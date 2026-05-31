const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry batchRegister", function () {
  const REGISTRATION_FEE = 1_000n;
  let registry;
  let user;

  beforeEach(async function () {
    [, user] = await ethers.getSigners();
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(REGISTRATION_FEE);
    await registry.waitForDeployment();
  });

  function getRegisteredEvents(receipt) {
    const eventTopic = registry.interface.getEvent("AgentRegistered").topicHash;
    return receipt.logs.filter(
      (log) => log.address === registry.target && log.topics[0] === eventTopic
    );
  }

  it("registers a batch of 1 agent", async function () {
    const names = ["agent-1"];
    const endpoints = ["https://agent-1.local"];

    const tx = await registry
      .connect(user)
      .batchRegister(names, endpoints, { value: REGISTRATION_FEE });
    const receipt = await tx.wait();
    const events = getRegisteredEvents(receipt);

    expect(events.length).to.equal(1);

    const parsed = registry.interface.parseLog(events[0]);
    const agentId = parsed.args.agentId;

    const agent = await registry.getAgent(agentId);
    expect(agent.owner).to.equal(user.address);
    expect(agent.name).to.equal(names[0]);
    expect(agent.endpoint).to.equal(endpoints[0]);
    expect(await ethers.provider.getBalance(registry.target)).to.equal(REGISTRATION_FEE);
  });

  it("registers a batch of 50 agents with unique IDs and events", async function () {
    const count = 50;
    const names = Array.from({ length: count }, (_, i) => `agent-${i + 1}`);
    const endpoints = Array.from(
      { length: count },
      (_, i) => `https://agent-${i + 1}.local`
    );
    const totalFee = REGISTRATION_FEE * BigInt(count);

    const tx = await registry
      .connect(user)
      .batchRegister(names, endpoints, { value: totalFee });
    const receipt = await tx.wait();
    const events = getRegisteredEvents(receipt);

    expect(events.length).to.equal(count);

    const ids = events.map((eventLog) => registry.interface.parseLog(eventLog).args.agentId);
    expect(new Set(ids).size).to.equal(count);

    const firstAgent = await registry.getAgent(ids[0]);
    const lastAgent = await registry.getAgent(ids[count - 1]);
    expect(firstAgent.name).to.equal(names[0]);
    expect(lastAgent.name).to.equal(names[count - 1]);
    expect(await ethers.provider.getBalance(registry.target)).to.equal(totalFee);
  });

  it("reverts on array length mismatch", async function () {
    await expect(
      registry.connect(user).batchRegister(
        ["agent-1", "agent-2"],
        ["https://agent-1.local"],
        { value: REGISTRATION_FEE * 2n }
      )
    ).to.be.revertedWith("Length mismatch");
  });
});
