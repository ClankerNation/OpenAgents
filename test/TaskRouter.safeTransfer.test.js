const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

const ARTIFACT_DIR = path.join(__dirname, "..", "build-issue181");

function loadArtifact(prefix) {
  const abi = JSON.parse(fs.readFileSync(path.join(ARTIFACT_DIR, `${prefix}.abi`), "utf8"));
  const bytecode = `0x${fs.readFileSync(path.join(ARTIFACT_DIR, `${prefix}.bin`), "utf8")}`;
  return { abi, bytecode };
}

describe("TaskRouter - ERC20 payout safety", function () {
  it("reverts completeTask when ERC20 transfer returns false", async function () {
    const [owner, creator, agentOwner] = await ethers.getSigners();

    const agentRegistryArtifact = loadArtifact("contracts_AgentRegistry_sol_AgentRegistry");
    const taskRouterArtifact = loadArtifact("contracts_TaskRouter_sol_TaskRouter");
    const mockTokenArtifact = loadArtifact("contracts_mocks_MockFalseERC20_sol_MockFalseERC20");

    const AgentRegistryFactory = new ethers.ContractFactory(agentRegistryArtifact.abi, agentRegistryArtifact.bytecode, owner);
    const registry = await AgentRegistryFactory.deploy(0);
    await registry.waitForDeployment();

    const TaskRouterFactory = new ethers.ContractFactory(taskRouterArtifact.abi, taskRouterArtifact.bytecode, owner);
    const taskRouter = await TaskRouterFactory.deploy(await registry.getAddress(), 500);
    await taskRouter.waitForDeployment();

    const MockTokenFactory = new ethers.ContractFactory(mockTokenArtifact.abi, mockTokenArtifact.bytecode, owner);
    const token = await MockTokenFactory.deploy();
    await token.waitForDeployment();

    const reward = 1_000n;
    await token.mint(creator.address, reward);
    await token.connect(creator).approve(await taskRouter.getAddress(), reward);

    const latest = await ethers.provider.getBlock("latest");
    const deadline = BigInt(latest.timestamp) + 3600n;

    await taskRouter.connect(creator).createTaskWithToken(
      await token.getAddress(),
      reward,
      "erc20-task",
      deadline
    );

    await registry.connect(agentOwner).registerAgent("agent-a", "https://agent", { value: 0 });
    const agentId = await registry.ownerAgents(agentOwner.address, 0);

    await taskRouter.connect(agentOwner).assignTask(0, agentId);
    await token.setFailTransfers(true);

    await expect(taskRouter.connect(agentOwner).completeTask(0, "0x1234")).to.be.reverted;

    const task = await taskRouter.tasks(0);
    expect(task.status).to.equal(1n); // Assigned
  });
});
