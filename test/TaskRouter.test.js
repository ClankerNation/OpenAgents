const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter SafeERC20", function () {
  let registry, token, router, owner, agent, creator;

  beforeEach(async function () {
    [owner, agent, creator] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy();

    const MockERC20 = await ethers.getContractFactory("MockERC20");
    token = await MockERC20.deploy("TestToken", "TT", 18);

    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    router = await TaskRouter.deploy(registry.target, 100, token.target); // 1% fee
  });

  it("should use safeTransfer on completeTask", async function () {
    // Register agent
    const agentId = ethers.encodeBytes32String("agent1");
    await registry.connect(agent).registerAgent("Test Agent", 100);

    // Create task
    await token.connect(creator).approve(router.target, 1000);
    const tx = await router.connect(creator).createTask("Test task", 0);
    const receipt = await tx.wait();
    const taskId = 0;

    // Assign task
    await router.connect(agent).assignTask(taskId, agentId);

    // Complete task - should use safeTransfer
    await expect(
      router.connect(agent).completeTask(taskId, "result")
    ).to.not.be.reverted;
  });

  it("should use safeTransfer on cancelTask", async function () {
    const agentId = ethers.encodeBytes32String("agent1");
    await registry.connect(agent).registerAgent("Test Agent", 100);

    // Create task
    await token.connect(creator).approve(router.target, 1000);
    await router.connect(creator).createTask("Test task", 0);
    const taskId = 0;

    // Cancel task - should use safeTransfer
    await expect(
      router.connect(creator).cancelTask(taskId)
    ).to.not.be.reverted;
  });

  it("should use safeTransfer on withdrawFees", async function () {
    // Setup task and complete it to generate fees
    const agentId = ethers.encodeBytes32String("agent1");
    await registry.connect(agent).registerAgent("Test Agent", 100);

    await token.connect(creator).approve(router.target, 1000);
    await router.connect(creator).createTask("Test task", 0);
    await router.connect(agent).assignTask(0, agentId);
    await router.connect(agent).completeTask(0, "done");

    // Withdraw fees - should use safeTransfer
    await expect(
      router.connect(owner).withdrawFees()
    ).to.not.be.reverted;
  });
});
