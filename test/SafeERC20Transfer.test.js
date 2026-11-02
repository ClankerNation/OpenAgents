const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter SafeERC20 transfers", function () {
  let taskRouter, agentRegistry, mockToken, nonRevertingToken;
  let owner, agent, creator;

  beforeEach(async function () {
    [owner, agent, creator] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    agentRegistry = await AgentRegistry.deploy(0);
    await agentRegistry.deployed();

    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    taskRouter = await TaskRouter.deploy(agentRegistry.target, 0);
    await taskRouter.deployed();

    // Use OpenZeppelin ERC20 as normal token
    const ERC20 = await ethers.getContractFactory("ERC20");
    mockToken = await ERC20.deploy("Mock Token", "MTK");
    await mockToken.deployed();

    // Mock non-reverting ERC20 that returns false on transfer
    const NonRevertingERC20 = await ethers.getContractFactory(
      "MockNonRevertingERC20"
    );
    nonRevertingToken = await NonRevertingERC20.deploy();
    await nonRevertingToken.deployed();

    // Set token on TaskRouter
    await taskRouter.setToken(mockToken.target);

    // Register agent
    await agentRegistry.registerAgent("Test Agent", "http://example.com", {
      value: ethers.parseEther("0.1"),
    });
  });

  it("should set and return the token address", async function () {
    expect(await taskRouter.token()).to.equal(mockToken.target);
  });

  it("should revert completeTask when token is not set", async function () {
    const NoTokenRouter = await ethers.getContractFactory("TaskRouter");
    const noTokenRouter = await NoTokenRouter.deploy(
      agentRegistry.target,
      0
    );
    await noTokenRouter.deployed();

    const taskId = await noTokenRouter
      .connect(creator)
      .createTask("test", Math.floor(Date.now() / 1000) + 86400, {
        value: ethers.parseEther("1"),
      });

    await noTokenRouter.connect(creator).assignTask(taskId, ethers.zeroHash);

    await expect(
      noTokenRouter.connect(agent).completeTask(taskId, "0x")
    ).to.be.revertedWith("Token not set");
  });

  it("should allow owner to set token", async function () {
    const NewToken = await ethers.getContractFactory("ERC20");
    const newToken = await NewToken.deploy("New Token", "NTK");
    await newToken.deployed();

    await taskRouter.connect(owner).setToken(newToken.target);
    expect(await taskRouter.token()).to.equal(newToken.target);
  });

  it("should revert when non-reverting ERC20 transfer returns false", async function () {
    // Switch to non-reverting token
    await taskRouter.connect(owner).setToken(nonRevertingToken.target);

    // Create and assign a task
    const taskId = await taskRouter
      .connect(creator)
      .createTask("test task", Math.floor(Date.now() / 1000) + 86400, {
        value: ethers.parseEther("1"),
      });

    await taskRouter.connect(creator).assignTask(taskId, ethers.zeroHash);

    // completeTask should revert because safeTransfer returns false
    await expect(
      taskRouter.connect(agent).completeTask(taskId, "0x")
    ).to.be.reverted;
  });

  it("should revert cancelTask when non-reverting ERC20 transfer returns false",
    async function () {
      // Switch to non-reverting token
      await taskRouter.connect(owner).setToken(nonRevertingToken.target);

      // Create an open task (no assignment needed for cancel by creator)
      const taskId = await taskRouter
        .connect(creator)
        .createTask("test task", Math.floor(Date.now() / 1000) + 86400, {
          value: ethers.parseEther("1"),
        });

      // cancelTask should revert because safeTransfer returns false
      await expect(
        taskRouter.connect(creator).cancelTask(taskId)
      ).to.be.reverted;
    }
  );
});
