const fs = require("fs");
const path = require("path");
const solc = require("solc");
const { expect } = require("chai");
const { ethers } = require("hardhat");

function compileRelayContracts() {
  const root = path.resolve(__dirname, "..");
  const sources = {
    "contracts/TaskRouter.sol": {
      content: fs.readFileSync(path.join(root, "contracts", "TaskRouter.sol"), "utf8")
    },
    "contracts/AgentRegistry.sol": {
      content: fs.readFileSync(path.join(root, "contracts", "AgentRegistry.sol"), "utf8")
    },
    "@openzeppelin/contracts/access/Ownable.sol": {
      content: fs.readFileSync(
        path.join(root, "node_modules", "@openzeppelin", "contracts", "access", "Ownable.sol"),
        "utf8"
      )
    },
    "@openzeppelin/contracts/utils/Context.sol": {
      content: fs.readFileSync(
        path.join(root, "node_modules", "@openzeppelin", "contracts", "utils", "Context.sol"),
        "utf8"
      )
    }
  };

  const input = {
    language: "Solidity",
    sources,
    settings: {
      optimizer: { enabled: false, runs: 200 },
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode.object"]
        }
      }
    }
  };

  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  if (output.errors) {
    const errors = output.errors.filter((entry) => entry.severity === "error");
    if (errors.length > 0) {
      throw new Error(errors.map((entry) => entry.formattedMessage).join("\n"));
    }
  }

  return {
    agentRegistry: output.contracts["contracts/AgentRegistry.sol"].AgentRegistry,
    taskRouter: output.contracts["contracts/TaskRouter.sol"].TaskRouter
  };
}

describe("TaskRouter gas sponsorship relay", function () {
  let registry;
  let router;
  let creator;
  let agentOwner;
  let relayer;
  let agentId;

  async function signRelayCall(signer, callData) {
    const nonce = await router.nonces(signer.address);
    const network = await ethers.provider.getNetwork();
    const digest = ethers.solidityPackedKeccak256(
      ["address", "uint256", "address", "uint256", "bytes32"],
      [await router.getAddress(), network.chainId, signer.address, nonce, ethers.keccak256(callData)]
    );
    return signer.signMessage(ethers.getBytes(digest));
  }

  beforeEach(async function () {
    const [deployer, creatorSigner, agentOwnerSigner, relayerSigner] = await ethers.getSigners();
    creator = creatorSigner;
    agentOwner = agentOwnerSigner;
    relayer = relayerSigner;

    const compiled = compileRelayContracts();

    const AgentRegistryFactory = new ethers.ContractFactory(
      compiled.agentRegistry.abi,
      `0x${compiled.agentRegistry.evm.bytecode.object}`,
      deployer
    );
    registry = await AgentRegistryFactory.deploy(0);
    await registry.waitForDeployment();

    const TaskRouterFactory = new ethers.ContractFactory(
      compiled.taskRouter.abi,
      `0x${compiled.taskRouter.evm.bytecode.object}`,
      deployer
    );
    router = await TaskRouterFactory.deploy(await registry.getAddress(), 0);
    await router.waitForDeployment();

    await registry.connect(agentOwner).registerAgent("agent-1", "https://agent.example");
    agentId = await registry.ownerAgents(agentOwner.address, 0);

    const latest = await ethers.provider.getBlock("latest");
    const deadline = latest.timestamp + 3600;
    await router.connect(creator).createTask("relayable task", deadline, {
      value: ethers.parseEther("1")
    });
  });

  it("sponsored execution: relayer can assign task for agent owner and gets reimbursed", async function () {
    await router.connect(agentOwner).stakeForGas({ value: ethers.parseEther("0.05") });

    const callData = router.interface.encodeFunctionData("assignTask", [0, agentId]);
    const signature = await signRelayCall(agentOwner, callData);

    const stakeBefore = await router.gasStake(agentOwner.address);
    const tx = await router.connect(relayer).executeOnBehalf(agentOwner.address, callData, signature);
    const receipt = await tx.wait();

    const stakeAfter = await router.gasStake(agentOwner.address);
    expect(stakeAfter).to.be.lt(stakeBefore);

    const task = await router.tasks(0);
    expect(task.status).to.equal(1n);
    expect(task.assignedAgent).to.equal(agentId);

    const relayed = receipt.logs
      .map((log) => {
        try {
          return router.interface.parseLog(log);
        } catch (error) {
          return null;
        }
      })
      .find((eventLog) => eventLog && eventLog.name === "RelayedExecution");

    expect(relayed).to.not.equal(undefined);
    expect(relayed.args.reimbursement).to.be.gt(0n);
    expect(relayed.args.relayer).to.equal(relayer.address);
  });

  it("replay prevention: same signature cannot be reused", async function () {
    await router.connect(agentOwner).stakeForGas({ value: ethers.parseEther("0.05") });

    const callData = router.interface.encodeFunctionData("assignTask", [0, agentId]);
    const signature = await signRelayCall(agentOwner, callData);

    await router.connect(relayer).executeOnBehalf(agentOwner.address, callData, signature);

    await expect(
      router.connect(relayer).executeOnBehalf(agentOwner.address, callData, signature)
    ).to.be.revertedWith("Invalid signature");
  });

  it("insufficient stake: relay reverts when agent stake cannot cover reimbursement", async function () {
    const callData = router.interface.encodeFunctionData("assignTask", [0, agentId]);
    const signature = await signRelayCall(agentOwner, callData);

    await expect(
      router.connect(relayer).executeOnBehalf(agentOwner.address, callData, signature)
    ).to.be.revertedWith("Insufficient gas stake");
  });
});
