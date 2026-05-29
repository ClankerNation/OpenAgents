const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");
const solc = require("solc");

function findImport(importPath) {
  const candidates = [
    path.join(process.cwd(), importPath),
    path.join(process.cwd(), "node_modules", importPath),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return { contents: fs.readFileSync(candidate, "utf8") };
    }
  }

  return { error: `File not found: ${importPath}` };
}

function compileAgentRegistry() {
  const sourcePath = "contracts/AgentRegistry.sol";
  const input = {
    language: "Solidity",
    sources: {
      [sourcePath]: { content: fs.readFileSync(sourcePath, "utf8") },
    },
    settings: {
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode.object"],
        },
      },
    },
  };

  const output = JSON.parse(solc.compile(JSON.stringify(input), { import: findImport }));
  const errors = (output.errors || []).filter((error) => error.severity === "error");
  if (errors.length) {
    throw new Error(errors.map((error) => error.formattedMessage).join("\n"));
  }

  return output.contracts[sourcePath].AgentRegistry;
}

async function deployRegistry(registrationFee) {
  const [owner] = await ethers.getSigners();
  const artifact = compileAgentRegistry();
  const factory = new ethers.ContractFactory(
    artifact.abi,
    `0x${artifact.evm.bytecode.object}`,
    owner
  );
  const contract = await factory.deploy(registrationFee);
  await contract.waitForDeployment();
  return contract;
}

describe("AgentRegistry batchRegister", function () {
  let user;
  let registry;
  const registrationFee = ethers.parseEther("0.01");

  beforeEach(async function () {
    [, user] = await ethers.getSigners();
    registry = await deployRegistry(registrationFee);
  });

  it("registers a batch of one", async function () {
    await expect(
      registry.connect(user).batchRegister(["one"], ["https://one.example"], {
        value: registrationFee,
      })
    ).to.emit(registry, "AgentRegistered");

    const ids = await registry.getAgentIds();
    expect(ids).to.have.length(1);
    const agent = await registry.getAgent(ids[0]);
    expect(agent.owner).to.equal(user.address);
    expect(agent.name).to.equal("one");
  });

  it("registers a batch of 50 agents with unique IDs", async function () {
    const names = [];
    const endpoints = [];
    for (let i = 0; i < 50; i++) {
      names.push(`agent-${i}`);
      endpoints.push(`https://agent-${i}.example`);
    }

    await registry.connect(user).batchRegister(names, endpoints, {
      value: registrationFee * 50n,
    });

    const ids = await registry.getAgentIds();
    expect(ids).to.have.length(50);
    expect(new Set(ids).size).to.equal(50);

    const lastAgent = await registry.getAgent(ids[49]);
    expect(lastAgent.name).to.equal("agent-49");
    expect(lastAgent.endpoint).to.equal("https://agent-49.example");
  });

  it("reverts on length mismatch", async function () {
    await expect(
      registry.connect(user).batchRegister(["one"], [], { value: registrationFee })
    ).to.be.revertedWith("Length mismatch");
  });

  it("requires the aggregate registration fee", async function () {
    await expect(
      registry.connect(user).batchRegister(["one", "two"], ["a", "b"], {
        value: registrationFee,
      })
    ).to.be.revertedWith("Insufficient fee");
  });
});
