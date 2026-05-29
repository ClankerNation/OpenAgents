const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");
const solc = require("solc");

function findImport(importPath) {
  const candidates = [
    path.join("node_modules", importPath),
    path.join(process.cwd(), importPath),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return { contents: fs.readFileSync(candidate, "utf8") };
    }
  }
  return { error: `File not found: ${importPath}` };
}

function compileRegistry() {
  const input = {
    language: "Solidity",
    sources: { "AgentRegistry.sol": { content: fs.readFileSync("contracts/AgentRegistry.sol", "utf8") } },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: { "*": { "*": ["abi", "evm.bytecode"] } },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input), { import: findImport }));
  const fatal = (output.errors || []).filter((error) => error.severity === "error");
  if (fatal.length > 0) {
    throw new Error(fatal.map((error) => error.formattedMessage).join("\n"));
  }
  return output.contracts["AgentRegistry.sol"].AgentRegistry;
}

async function deployRegistry() {
  const [owner] = await ethers.getSigners();
  const compiled = compileRegistry();
  const factory = new ethers.ContractFactory(compiled.abi, compiled.evm.bytecode.object, owner);
  const registry = await factory.deploy(0);
  await registry.waitForDeployment();
  return registry;
}

async function register(registry, signer, name) {
  const tx = await registry.connect(signer).registerAgent(name, `https://${name}.example`);
  const receipt = await tx.wait();
  const event = receipt.logs
    .map((log) => {
      try {
        return registry.interface.parseLog(log);
      } catch (_) {
        return null;
      }
    })
    .find((log) => log && log.name === "AgentRegistered");
  return event.args.agentId;
}

describe("AgentRegistry active count and pagination", function () {
  it("maintains activeCount in O(1) as agents are registered and deactivated", async function () {
    const [owner, alice] = await ethers.getSigners();
    const registry = await deployRegistry();

    const first = await register(registry, owner, "alpha");
    await register(registry, alice, "beta");

    expect(await registry.getActiveAgentCount()).to.equal(2n);
    await expect(registry.deactivateAgent(first))
      .to.emit(registry, "AgentDeactivated")
      .withArgs(first);

    expect(await registry.getActiveAgentCount()).to.equal(1n);
    await expect(registry.deactivateAgent(first)).to.be.revertedWith("Agent inactive");
  });

  it("paginates all agents and owner-specific agents", async function () {
    const [owner, alice] = await ethers.getSigners();
    const registry = await deployRegistry();

    const first = await register(registry, owner, "alpha");
    const second = await register(registry, owner, "beta");
    const third = await register(registry, alice, "gamma");

    expect(await registry.getAgents(1, 2)).to.deep.equal([second, third]);
    expect(await registry.getAgents(99, 10)).to.deep.equal([]);
    expect(await registry.getAgentsByOwner(owner.address, 0, 10)).to.deep.equal([first, second]);
    expect(await registry.getAgentsByOwner(alice.address, 0, 10)).to.deep.equal([third]);
  });
});
