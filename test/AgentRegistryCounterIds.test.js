const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry counter IDs", function () {
  it("gives two same-name registrations unique IDs", async function () {
    const [firstOwner, secondOwner] = await ethers.getSigners();
    const Registry = await ethers.getContractFactory("AgentRegistry");
    const registry = await Registry.deploy(0);

    const first = await registry.connect(firstOwner).registerAgent("same-name", "https://one.example");
    const second = await registry.connect(secondOwner).registerAgent("same-name", "https://two.example");

    const firstReceipt = await first.wait();
    const secondReceipt = await second.wait();
    const firstEvent = firstReceipt.logs
      .map((log) => registry.interface.parseLog(log))
      .find((log) => log.name === "AgentRegistered");
    const secondEvent = secondReceipt.logs
      .map((log) => registry.interface.parseLog(log))
      .find((log) => log.name === "AgentRegistered");

    expect(firstEvent.args.agentId).to.not.equal(secondEvent.args.agentId);
    expect(firstEvent.args.agentId).to.equal(ethers.zeroPadValue("0x01", 32));
    expect(secondEvent.args.agentId).to.equal(ethers.zeroPadValue("0x02", 32));
    expect(await registry.nextAgentId()).to.equal(3);
  });
});
