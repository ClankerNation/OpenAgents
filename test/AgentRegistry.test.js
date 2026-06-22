const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry", function () {
  async function deployRegistry(registrationFee = 0n) {
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    const registry = await AgentRegistry.deploy(registrationFee);
    await registry.waitForDeployment();
    return registry;
  }

  it("assigns unique counter-based ids for same owner and same name", async function () {
    const [owner] = await ethers.getSigners();
    const registry = await deployRegistry();

    const first = await registry.registerAgent.staticCall("same-name", "https://agent-one.example");
    await registry.registerAgent("same-name", "https://agent-one.example");

    const second = await registry.registerAgent.staticCall("same-name", "https://agent-two.example");
    await registry.registerAgent("same-name", "https://agent-two.example");

    expect(first).to.not.equal(second);
    expect(first).to.equal(ethers.zeroPadValue(ethers.toBeHex(1), 32));
    expect(second).to.equal(ethers.zeroPadValue(ethers.toBeHex(2), 32));

    const firstAgent = await registry.getAgent(first);
    const secondAgent = await registry.getAgent(second);
    expect(firstAgent.owner).to.equal(owner.address);
    expect(secondAgent.owner).to.equal(owner.address);
    expect(firstAgent.name).to.equal("same-name");
    expect(secondAgent.name).to.equal("same-name");
    expect(firstAgent.endpoint).to.equal("https://agent-one.example");
    expect(secondAgent.endpoint).to.equal("https://agent-two.example");
  });

  it("keeps registration fee and owner agent list behavior unchanged", async function () {
    const [owner] = await ethers.getSigners();
    const fee = ethers.parseEther("0.01");
    const registry = await deployRegistry(fee);

    await expect(registry.registerAgent("paid-agent", "https://paid.example"))
      .to.be.revertedWith("Insufficient fee");

    const agentId = await registry.registerAgent.staticCall("paid-agent", "https://paid.example", { value: fee });
    await registry.registerAgent("paid-agent", "https://paid.example", { value: fee });

    expect(await registry.ownerAgents(owner.address, 0)).to.equal(agentId);
    const agent = await registry.getAgent(agentId);
    expect(agent.active).to.equal(true);
    expect(agent.reputation).to.equal(100n);
  });
});
