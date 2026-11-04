const { expect } = require("chai");
const { ethers } = require("hardhat");

// @contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
// @platform full verbatim block: header of contracts/AgentRegistry.sol
// @runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
//   shell=C:\Program Files\Git\bin\bash.exe
// @date 2026-11-04T20:35:00Z

const FEE = ethers.parseEther("0.01");

async function deploy() {
  const [admin, alice, bob] = await ethers.getSigners();
  const Registry = await ethers.getContractFactory("AgentRegistry");
  const registry = await Registry.deploy(FEE);
  await registry.waitForDeployment();
  return { registry, admin, alice, bob };
}

describe("AgentRegistry deterministic ids", function () {
  it("hands out sequential ids", async function () {
    const { registry, alice } = await deploy();
    expect(await registry.nextAgentId()).to.equal(1n);

    await registry.connect(alice).registerAgent("one", "https://a", { value: FEE });
    await registry.connect(alice).registerAgent("two", "https://b", { value: FEE });

    expect(await registry.nextAgentId()).to.equal(3n);
    const first = await registry.ownerAgents(alice.address, 0);
    const second = await registry.ownerAgents(alice.address, 1);
    expect(first).to.equal(ethers.toBeHex(1n, 32));
    expect(second).to.equal(ethers.toBeHex(2n, 32));
  });

  it("allows the same name twice in the same block by the same sender", async function () {
    const { registry, alice } = await deploy();
    // no block mined between the two calls: the old timestamp hash collided here
    await registry.connect(alice).registerAgent("same", "https://a", { value: FEE });
    await registry.connect(alice).registerAgent("same", "https://b", { value: FEE });

    const first = await registry.ownerAgents(alice.address, 0);
    const second = await registry.ownerAgents(alice.address, 1);
    expect(first).to.not.equal(second);
    expect((await registry.agents(first)).endpoint).to.equal("https://a");
    expect((await registry.agents(second)).endpoint).to.equal("https://b");
  });

  it("lets two senders use the same name", async function () {
    const { registry, alice, bob } = await deploy();
    await registry.connect(alice).registerAgent("shared", "https://a", { value: FEE });
    await registry.connect(bob).registerAgent("shared", "https://b", { value: FEE });

    expect(await registry.ownerAgents(alice.address, 0)).to.not.equal(
      await registry.ownerAgents(bob.address, 0)
    );
  });

  it("resolves an owner's id by name", async function () {
    const { registry, alice } = await deploy();
    await registry.connect(alice).registerAgent("lookup", "https://a", { value: FEE });

    const id = await registry.agentIdOf(alice.address, "lookup");
    expect((await registry.agents(id)).name).to.equal("lookup");
    expect(await registry.agentIdOf(alice.address, "missing")).to.equal(ethers.ZeroHash);
  });

  it("returns the newest id when a name repeats", async function () {
    const { registry, alice } = await deploy();
    await registry.connect(alice).registerAgent("dup", "https://old", { value: FEE });
    await registry.connect(alice).registerAgent("dup", "https://new", { value: FEE });

    const id = await registry.agentIdOf(alice.address, "dup");
    expect((await registry.agents(id)).endpoint).to.equal("https://new");
  });

  it("still enforces the fee and name rules", async function () {
    const { registry, alice } = await deploy();
    await expect(registry.connect(alice).registerAgent("x", "https://a", { value: 1n })).to.be.revertedWith(
      "Insufficient fee"
    );
    await expect(
      registry.connect(alice).registerAgent("", "https://a", { value: FEE })
    ).to.be.revertedWith("Invalid name");
    await expect(
      registry.connect(alice).registerAgent("y".repeat(65), "https://a", { value: FEE })
    ).to.be.revertedWith("Invalid name");
  });

  it("emits the sequential id", async function () {
    const { registry, alice } = await deploy();
    await expect(registry.connect(alice).registerAgent("ev", "https://a", { value: FEE }))
      .to.emit(registry, "AgentRegistered")
      .withArgs(ethers.toBeHex(1n, 32), alice.address, "ev");
  });

  it("starts fresh agents as active with the default reputation", async function () {
    const { registry, alice } = await deploy();
    await registry.connect(alice).registerAgent("fresh", "https://a", { value: FEE });
    const agent = await registry.agents(await registry.ownerAgents(alice.address, 0));
    expect(agent.active).to.equal(true);
    expect(agent.reputation).to.equal(100n);
    expect(agent.owner).to.equal(alice.address);
  });
});
