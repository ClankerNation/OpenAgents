const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry counter-based IDs", function () {
  let registry;
  let owner;
  let agentOwner;
  let otherOwner;

  const registrationFee = ethers.parseEther("0.01");

  beforeEach(async function () {
    [owner, agentOwner, otherOwner] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(registrationFee);
    await registry.waitForDeployment();
  });

  it("keeps the existing registration flow and stores the registered agent", async function () {
    await expect(
      registry.connect(agentOwner).registerAgent("alpha", "https://alpha.example", { value: registrationFee })
    )
      .to.emit(registry, "AgentRegistered")
      .withArgs(ethers.toBeHex(1, 32), agentOwner.address, "alpha");

    expect(await registry.nextAgentId()).to.equal(1n);
    expect(await registry.ownerAgents(agentOwner.address, 0)).to.equal(ethers.toBeHex(1, 32));

    const agent = await registry.getAgent(ethers.toBeHex(1, 32));
    expect(agent.owner).to.equal(agentOwner.address);
    expect(agent.name).to.equal("alpha");
    expect(agent.endpoint).to.equal("https://alpha.example");
    expect(agent.reputation).to.equal(100n);
    expect(agent.tasksCompleted).to.equal(0n);
    expect(agent.active).to.equal(true);
  });

  it("assigns unique IDs for identical names registered by the same sender in the same block", async function () {
    const registryAddress = await registry.getAddress();
    const nonce = await ethers.provider.getTransactionCount(agentOwner.address);

    await ethers.provider.send("evm_setAutomine", [false]);
    let firstTx;
    let secondTx;
    try {
      firstTx = await registry.connect(agentOwner).registerAgent("same-name", "ipfs://one", {
        value: registrationFee,
        nonce,
      });
      secondTx = await registry.connect(agentOwner).registerAgent("same-name", "ipfs://two", {
        value: registrationFee,
        nonce: nonce + 1,
      });
      await ethers.provider.send("evm_mine", []);
    } finally {
      await ethers.provider.send("evm_setAutomine", [true]);
    }

    const firstReceipt = await firstTx.wait();
    const secondReceipt = await secondTx.wait();
    expect(firstReceipt.blockNumber).to.equal(secondReceipt.blockNumber);

    const firstId = await registry.ownerAgents(agentOwner.address, 0);
    const secondId = await registry.ownerAgents(agentOwner.address, 1);
    expect(firstId).to.equal(ethers.toBeHex(1, 32));
    expect(secondId).to.equal(ethers.toBeHex(2, 32));
    expect(firstId).to.not.equal(secondId);

    const firstAgent = await registry.getAgent(firstId);
    const secondAgent = await registry.getAgent(secondId);
    expect(firstAgent.owner).to.equal(agentOwner.address);
    expect(secondAgent.owner).to.equal(agentOwner.address);
    expect(firstAgent.name).to.equal("same-name");
    expect(secondAgent.name).to.equal("same-name");
    expect(firstAgent.endpoint).to.equal("ipfs://one");
    expect(secondAgent.endpoint).to.equal("ipfs://two");
    expect(await ethers.provider.getBalance(registryAddress)).to.equal(registrationFee * 2n);
  });

  it("uses the same counter across different owners", async function () {
    await registry.connect(agentOwner).registerAgent("alpha", "https://alpha.example", { value: registrationFee });
    await registry.connect(otherOwner).registerAgent("alpha", "https://other.example", { value: registrationFee });

    const firstId = await registry.ownerAgents(agentOwner.address, 0);
    const secondId = await registry.ownerAgents(otherOwner.address, 0);
    expect(firstId).to.equal(ethers.toBeHex(1, 32));
    expect(secondId).to.equal(ethers.toBeHex(2, 32));
    expect(await registry.nextAgentId()).to.equal(2n);
  });
});
