const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter SafeERC20", function () {
  let router, registry, token;
  let admin, creator, agentOwner;
  const FEE = ethers.parseEther("0.01");
  const REWARD = ethers.parseEther("100");

  beforeEach(async function () {
    [admin, creator, agentOwner] = await ethers.getSigners();

    const RegistryFactory = await ethers.getContractFactory("AgentRegistry");
    registry = await RegistryFactory.deploy(FEE);
    await registry.waitForDeployment();

    const RouterFactory = await ethers.getContractFactory("TaskRouter");
    router = await RouterFactory.deploy(registry.target, 100); // 1% fee
    await router.waitForDeployment();

    const TokenFactory = await ethers.getContractFactory("MockNonRevertingERC20");
    token = await TokenFactory.deploy();
    await token.waitForDeployment();
    
    // Admin has all tokens, transfer some to creator
    await token.transfer(creator.address, ethers.parseEther("1000"));
    
    // Register an agent
    await registry.connect(agentOwner).registerAgent("TestAgent", "https://test.com", { value: FEE });
  });

  it("should revert completeTask if non-reverting token transfer fails", async function () {
    // Approve router to spend tokens
    await token.connect(creator).approve(router.target, REWARD);
    
    // Create task with token
    const tx = await router.connect(creator).createTaskWithToken("Test task", Math.floor(Date.now()/1000) + 86400, token.target, REWARD);
    await tx.wait();
    const taskId = await router.taskCount() - 1n;
    
    // Get agent ID
    const agentId = await registry.agentIds(0);
    
    // Assign
    await router.connect(agentOwner).assignTask(taskId, agentId);
    
    // Set token to fail
    await token.setShouldFail(true);
    
    // Complete should revert because safeTransfer will revert when transfer returns false
    await expect(router.connect(agentOwner).completeTask(taskId, "0x1234"))
      .to.be.reverted;
  });

  it("should succeed completeTask if token transfer works", async function () {
    await token.connect(creator).approve(router.target, REWARD);
    const tx = await router.connect(creator).createTaskWithToken("Test task", Math.floor(Date.now()/1000) + 86400, token.target, REWARD);
    await tx.wait();
    const taskId = await router.taskCount() - 1n;
    
    const agentId = await registry.agentIds(0);
    await router.connect(agentOwner).assignTask(taskId, agentId);
    
    await token.setShouldFail(false);
    
    await expect(router.connect(agentOwner).completeTask(taskId, "0x1234"))
      .to.emit(router, "TaskCompleted");
  });
});
