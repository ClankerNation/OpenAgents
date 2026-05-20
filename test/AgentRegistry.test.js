const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry", function () {
  async function deployFixture() {
    const [owner, alice, bob] = await ethers.getSigners();
    const fee = ethers.parseEther("0.01");

    const AgentRegistry = await ethers.getContractFactory("AgentRegistryHarness");
    const registry = await AgentRegistry.deploy(fee);
    await registry.waitForDeployment();

    return { owner, alice, bob, fee, registry };
  }

  async function register(registry, signer, fee, name) {
    await registry.connect(signer).registerAgent(name, `https://${name}.example`, { value: fee });
    const ids = await registry.getAgentsByOwner(signer.address);
    return ids[ids.length - 1];
  }

  it("keeps active agent count accurate without scanning all ids", async function () {
    const { alice, bob, fee, registry } = await deployFixture();

    const aliceOne = await register(registry, alice, fee, "alice-one");
    await register(registry, alice, fee, "alice-two");
    await register(registry, bob, fee, "bob-one");

    expect(await registry.activeCount()).to.equal(3);
    expect(await registry.getActiveAgentCount()).to.equal(3);

    await registry.connect(alice).deactivateAgent(aliceOne);

    expect(await registry.activeCount()).to.equal(2);
    expect(await registry.getActiveAgentCount()).to.equal(2);
    await expect(registry.connect(alice).deactivateAgent(aliceOne)).to.be.revertedWith("Already inactive");
  });

  it("paginates agent ids with total count and bound checks", async function () {
    const { alice, bob, fee, registry } = await deployFixture();
    const first = await register(registry, alice, fee, "alice-one");
    const second = await register(registry, alice, fee, "alice-two");
    const third = await register(registry, bob, fee, "bob-one");

    let page = await registry.getAgentIds(1, 2);
    expect(page.total).to.equal(3);
    expect(page.ids).to.deep.equal([second, third]);

    page = await registry.getAgentIds(10, 2);
    expect(page.total).to.equal(3);
    expect(page.ids).to.deep.equal([]);

    page = await registry.getAgentIds(0, 0);
    expect(page.total).to.equal(3);
    expect(page.ids).to.deep.equal([]);

    page = await registry.getAgentIds(0, 500);
    expect(page.total).to.equal(3);
    expect(page.ids).to.deep.equal([first, second, third]);
  });

  it("filters agents by owner", async function () {
    const { alice, bob, fee, registry } = await deployFixture();
    const aliceOne = await register(registry, alice, fee, "alice-one");
    const aliceTwo = await register(registry, alice, fee, "alice-two");
    const bobOne = await register(registry, bob, fee, "bob-one");

    expect(await registry.getAgentsByOwner(alice.address)).to.deep.equal([aliceOne, aliceTwo]);
    expect(await registry.getAgentsByOwner(bob.address)).to.deep.equal([bobOne]);
  });
});
