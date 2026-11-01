const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter SafeERC20 transfers", function () {
  let taskRouter, agentRegistry, mockToken;
  let owner, agent, creator;

  beforeEach(async function () {
    [owner, agent, creator] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    agentRegistry = await AgentRegistry.deploy(0);
    await agentRegistry.deployed();

    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    taskRouter = await TaskRouter.deploy(agentRegistry.target, 0);
    await taskRouter.deployed();

    // Use OpenZeppelin ERC20 directly as the mock token
    const ERC20 = await ethers.getContractFactory("ERC20");
    mockToken = await ERC20.deploy("Mock Token", "MTK");
    await mockToken.deployed();

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
});
