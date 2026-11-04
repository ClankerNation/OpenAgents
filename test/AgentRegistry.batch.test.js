const { expect } = require("chai");
const { ethers } = require("hardhat");

// @contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
// @platform-config full verbatim block: header of contracts/AgentRegistry.sol
// @env os=windows arch=x86_64 home_dir=C:\Users\2
//   working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa shell=C:\Program Files\Git\bin\bash.exe
// @timestamp 2026-11-04T15:45:00Z

const FEE = ethers.parseEther("0.01");
const names = (n, prefix = "agent") => Array.from({ length: n }, (_, i) => `${prefix}-${i}`);
const endpoints = (n) => Array.from({ length: n }, (_, i) => `https://a${i}.example.com`);

async function deploy() {
  const [owner, alice] = await ethers.getSigners();
  const Registry = await ethers.getContractFactory("AgentRegistry");
  const registry = await Registry.deploy(FEE);
  await registry.waitForDeployment();
  return { registry, owner, alice };
}

describe("AgentRegistry.batchRegister", function () {
  it("registers a single agent in a batch and emits its event", async function () {
    const { registry, alice } = await deploy();
    const ns = ["solo"];
    const es = ["https://solo.example.com"];

    const receipt = await (await registry.connect(alice).batchRegister(ns, es, { value: FEE })).wait();
    const event = registry.interface.parseLog(receipt.logs[0]);
    const id = event.args.agentId;

    expect(event.name).to.equal("AgentRegistered");
    expect(await registry.ownerAgents(alice.address, 0)).to.equal(id);
    expect((await registry.agents(id)).name).to.equal("solo");
    expect((await registry.agents(id)).owner).to.equal(alice.address);
  });

  it("registers 50 agents in one transaction and collects the fee once", async function () {
    const { registry, alice } = await deploy();
    const ns = names(50);
    const es = endpoints(50);
    const total = FEE * 50n;

    const tx = registry.connect(alice).batchRegister(ns, es, { value: total });
    await expect(tx).to.changeEtherBalances([alice, registry], [-total, total]);

    const receipt = await (await tx).wait();
    expect(receipt.logs.length).to.equal(50);

    const ids = receipt.logs.map((log) => registry.interface.parseLog(log).args.agentId);
    expect(new Set(ids).size).to.equal(50);
    expect(await registry.ownerAgents(alice.address, 0)).to.equal(ids[0]);
  });

  it("each registration in a batch gets its own event with its own id", async function () {
    const { registry, alice } = await deploy();
    const ns = names(3);
    const es = endpoints(3);

    const receipt = await (await registry.connect(alice).batchRegister(ns, es, { value: FEE * 3n })).wait();
    const parsed = receipt.logs.map((log) => registry.interface.parseLog(log));
    const ids = parsed.map((entry) => entry.args.agentId);

    expect(parsed.every((entry) => entry.name === "AgentRegistered")).to.equal(true);
    expect(new Set(ids).size).to.equal(3);
    for (let i = 0; i < 3; i += 1) {
      expect(parsed[i].args.owner).to.equal(alice.address);
      expect(parsed[i].args.name).to.equal(ns[i]);
    }
  });

  it("reverts when the arrays differ in length", async function () {
    const { registry, alice } = await deploy();
    await expect(
      registry.connect(alice).batchRegister(names(3), endpoints(2), { value: FEE * 3n })
    ).to.be.revertedWith("Length mismatch");
  });

  it("reverts when the batch is empty", async function () {
    const { registry, alice } = await deploy();
    await expect(registry.connect(alice).batchRegister([], [], { value: 0 })).to.be.revertedWith(
      "Batch size 1-50"
    );
  });

  it("reverts above 50 agents", async function () {
    const { registry, alice } = await deploy();
    await expect(
      registry.connect(alice).batchRegister(names(51), endpoints(51), { value: FEE * 51n })
    ).to.be.revertedWith("Batch size 1-50");
  });

  it("charges the fee per agent, not per call", async function () {
    const { registry, alice } = await deploy();
    const ns = names(5);
    const es = endpoints(5);

    await expect(
      registry.connect(alice).batchRegister(ns, es, { value: FEE * 5n - 1n })
    ).to.be.revertedWith("Insufficient fee");

    await expect(registry.connect(alice).batchRegister(ns, es, { value: FEE * 5n })).to.not.be.reverted;
  });

  it("rejects a duplicate name inside one batch", async function () {
    const { registry, alice } = await deploy();
    await expect(
      registry.connect(alice).batchRegister(["dup", "dup"], endpoints(2), { value: FEE * 2n })
    ).to.be.revertedWith("Agent exists");
  });

  it("rejects an over-long name and an empty name", async function () {
    const { registry, alice } = await deploy();
    await expect(
      registry.connect(alice).batchRegister([""], endpoints(1), { value: FEE })
    ).to.be.revertedWith("Invalid name");
    await expect(
      registry.connect(alice).batchRegister(["x".repeat(65)], endpoints(1), { value: FEE })
    ).to.be.revertedWith("Invalid name");
  });

  it("leaves the single registration path working", async function () {
    const { registry, alice } = await deploy();
    await expect(registry.connect(alice).registerAgent("single", "https://s.example.com", { value: FEE }))
      .to.emit(registry, "AgentRegistered");
  });
});
