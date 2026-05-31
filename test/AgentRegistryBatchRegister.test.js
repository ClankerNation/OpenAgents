const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry.batchRegister", function () {
  const REGISTRATION_FEE = ethers.parseEther("0.01");

  async function deployRegistry() {
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    const registry = await AgentRegistry.deploy(REGISTRATION_FEE);
    await registry.waitForDeployment();
    return registry;
  }

  function getRegisteredEvents(registry, receipt) {
    return receipt.logs
      .map((log) => {
        try {
          return registry.interface.parseLog(log);
        } catch {
          return null;
        }
      })
      .filter((event) => event && event.name === "AgentRegistered");
  }

  it("registers a batch of 1 agent with one transaction", async function () {
    const [, user] = await ethers.getSigners();
    const registry = await deployRegistry();
    const names = ["agent-one"];
    const endpoints = ["https://agent.one"];

    const tx = await registry
      .connect(user)
      .batchRegister(names, endpoints, { value: REGISTRATION_FEE });
    const receipt = await tx.wait();
    const events = getRegisteredEvents(registry, receipt);

    expect(events).to.have.lengthOf(1);
    const agentId = events[0].args.agentId;

    expect(await registry.getActiveAgentCount()).to.equal(1n);
    expect(await ethers.provider.getBalance(await registry.getAddress())).to.equal(
      REGISTRATION_FEE
    );

    const agent = await registry.getAgent(agentId);
    expect(agent.owner).to.equal(user.address);
    expect(agent.name).to.equal("agent-one");
    expect(agent.endpoint).to.equal("https://agent.one");
    expect(agent.active).to.equal(true);
  });

  it("registers 50 agents in one transaction with unique IDs and events", async function () {
    const [, user] = await ethers.getSigners();
    const registry = await deployRegistry();

    const names = Array.from({ length: 50 }, (_, i) => `agent-${i + 1}`);
    const endpoints = Array.from({ length: 50 }, (_, i) => `https://agent-${i + 1}.example`);
    const totalFee = REGISTRATION_FEE * 50n;

    const tx = await registry.connect(user).batchRegister(names, endpoints, { value: totalFee });
    const receipt = await tx.wait();
    const events = getRegisteredEvents(registry, receipt);

    expect(events).to.have.lengthOf(50);

    const ids = events.map((event) => event.args.agentId);
    expect(new Set(ids).size).to.equal(50);
    expect(await registry.getActiveAgentCount()).to.equal(50n);
    expect(await ethers.provider.getBalance(await registry.getAddress())).to.equal(totalFee);
  });

  it("reverts when names/endpoints array lengths mismatch", async function () {
    const [, user] = await ethers.getSigners();
    const registry = await deployRegistry();

    await expect(
      registry
        .connect(user)
        .batchRegister(["agent-a", "agent-b"], ["https://agent-a.example"], {
          value: REGISTRATION_FEE * 2n,
        })
    ).to.be.revertedWith("Length mismatch");
  });
});
