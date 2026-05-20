const { expect } = require("chai");
const { ethers, network } = require("hardhat");

describe("AgentRegistry", function () {
  async function deployRegistry(registrationFee = 0n) {
    const [owner, registrant] = await ethers.getSigners();
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    const registry = await AgentRegistry.deploy(registrationFee);
    await registry.waitForDeployment();
    return { owner, registrant, registry };
  }

  afterEach(async function () {
    await network.provider.send("evm_setAutomine", [true]);
  });

  it("keeps the honest registration flow unchanged", async function () {
    const { registrant, registry } = await deployRegistry();

    await registry.connect(registrant).registerAgent("alpha", "https://agent.example");
    const agentId = await registry.ownerAgents(registrant.address, 0);
    const agent = await registry.getAgent(agentId);

    expect(agent.owner).to.equal(registrant.address);
    expect(agent.name).to.equal("alpha");
    expect(agent.endpoint).to.equal("https://agent.example");
    expect(agent.active).to.equal(true);
  });

  it("gives two same-name same-block registrations different ids", async function () {
    const { registrant, registry } = await deployRegistry();
    const startNonce = await ethers.provider.getTransactionCount(registrant.address);

    await network.provider.send("evm_setAutomine", [false]);
    const firstTx = await registry
      .connect(registrant)
      .registerAgent("alpha", "https://one.example", { nonce: startNonce });
    const secondTx = await registry
      .connect(registrant)
      .registerAgent("alpha", "https://two.example", { nonce: startNonce + 1 });
    await network.provider.send("evm_mine");
    await network.provider.send("evm_setAutomine", [true]);

    await firstTx.wait();
    await secondTx.wait();

    const firstId = await registry.ownerAgents(registrant.address, 0);
    const secondId = await registry.ownerAgents(registrant.address, 1);
    const first = await registry.getAgent(firstId);
    const second = await registry.getAgent(secondId);

    expect(firstId).to.not.equal(secondId);
    expect(first.name).to.equal("alpha");
    expect(second.name).to.equal("alpha");
    expect(first.registeredAt).to.equal(second.registeredAt);
  });
});
