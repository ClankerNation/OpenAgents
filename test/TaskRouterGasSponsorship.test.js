const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");
const solc = require("solc");

function findImport(importPath) {
  const candidates = [
    path.join(process.cwd(), importPath),
    path.join(process.cwd(), "node_modules", importPath),
    path.join(process.cwd(), "contracts", importPath),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return { contents: fs.readFileSync(candidate, "utf8") };
    }
  }

  return { error: `File not found: ${importPath}` };
}

function compileContracts() {
  const registryPath = "contracts/AgentRegistry.sol";
  const routerPath = "contracts/TaskRouter.sol";
  const input = {
    language: "Solidity",
    sources: {
      [registryPath]: { content: fs.readFileSync(registryPath, "utf8") },
      [routerPath]: { content: fs.readFileSync(routerPath, "utf8") },
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

  return {
    registry: output.contracts[registryPath].AgentRegistry,
    router: output.contracts[routerPath].TaskRouter,
  };
}

async function deploy(artifact, signer, args = []) {
  const factory = new ethers.ContractFactory(
    artifact.abi,
    `0x${artifact.evm.bytecode.object}`,
    signer
  );
  const contract = await factory.deploy(...args);
  await contract.waitForDeployment();
  return contract;
}

async function signSponsored(router, agent, callData) {
  const nonce = await router.agentNonces(agent.address);
  const chainId = (await ethers.provider.getNetwork()).chainId;
  const messageHash = ethers.solidityPackedKeccak256(
    ["uint256", "address", "address", "uint256", "bytes"],
    [chainId, await router.getAddress(), agent.address, nonce, callData]
  );
  return agent.signMessage(ethers.getBytes(messageHash));
}

describe("TaskRouter gas sponsorship", function () {
  let compiled;
  let creator;
  let agent;
  let relayer;
  let registry;
  let router;
  let agentId;

  before(function () {
    compiled = compileContracts();
  });

  beforeEach(async function () {
    [creator, agent, relayer] = await ethers.getSigners();
    registry = await deploy(compiled.registry, creator, [0]);
    router = await deploy(compiled.router, creator, [await registry.getAddress(), 0]);

    const receipt = await (await registry.connect(agent).registerAgent("agent", "https://agent.example")).wait();
    agentId = receipt.logs
      .map((log) => {
        try {
          return registry.interface.parseLog(log);
        } catch (_error) {
          return null;
        }
      })
      .find((log) => log && log.name === "AgentRegistered").args.agentId;

    await router.connect(creator).createTask("do work", (await timeNow()) + 3600, {
      value: ethers.parseEther("1"),
    });
    await router.connect(agent).assignTask(0, agentId);
  });

  it("executes an agent-signed task completion through a relayer", async function () {
    await router.connect(agent).depositStake({ value: ethers.parseEther("0.1") });
    const callData = router.interface.encodeFunctionData("completeTask", [0, "0x1234"]);
    const signature = await signSponsored(router, agent, callData);

    await expect(router.connect(relayer).executeOnBehalf(agent.address, callData, signature))
      .to.emit(router, "SponsoredExecution");

    const task = await router.tasks(0);
    expect(task.status).to.equal(2);
    expect(await router.agentNonces(agent.address)).to.equal(1);
    expect(await router.agentStake(agent.address)).to.be.lessThan(ethers.parseEther("0.1"));
  });

  it("rejects replayed sponsored executions", async function () {
    await router.connect(agent).depositStake({ value: ethers.parseEther("0.1") });
    const callData = router.interface.encodeFunctionData("completeTask", [0, "0x1234"]);
    const signature = await signSponsored(router, agent, callData);

    await router.connect(relayer).executeOnBehalf(agent.address, callData, signature);
    await expect(router.connect(relayer).executeOnBehalf(agent.address, callData, signature))
      .to.be.revertedWith("Invalid signature");
  });

  it("reverts if the agent stake cannot reimburse the relayer", async function () {
    const callData = router.interface.encodeFunctionData("completeTask", [0, "0x1234"]);
    const signature = await signSponsored(router, agent, callData);

    await expect(router.connect(relayer).executeOnBehalf(agent.address, callData, signature))
      .to.be.revertedWith("Insufficient stake");
  });
});

async function timeNow() {
  const block = await ethers.provider.getBlock("latest");
  return block.timestamp;
}
