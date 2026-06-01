const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter — SafeERC20 transfer handling", function () {
  let router, registry, owner, creator;

  beforeEach(async function () {
    [owner, creator] = await ethers.getSigners();

    const Registry = await ethers.getContractFactory("AgentRegistry");
    registry = await Registry.deploy(ethers.parseEther("0.01"));
    await registry.waitForDeployment();

    const Router = await ethers.getContractFactory("TaskRouter");
    router = await Router.deploy(await registry.getAddress(), 100); // 1% fee
    await router.waitForDeployment();
  });

  it("completes task and transfers reward successfully", async function () {
    const reward = ethers.parseEther("1");

    // Create task
    const tx1 = await router.connect(creator).createTask(
      "Test task",
      Math.floor(Date.now() / 1000) + 86400,
      { value: reward }
    );
    const receipt1 = await tx1.wait();
    const taskId = receipt1.logs.find(
      (l) => l.fragment && l.fragment.name === "TaskCreated"
    ).args.taskId;

    expect(await ethers.provider.getBalance(await router.getAddress()))
      .to.equal(reward);

    // Register agent
    await registry.registerAgent("agent1", "https://agent.example", { value: ethers.parseEther("0.01") });
    const agentIds = await registry.agentIds(0);

    // Assign
    await router.connect(creator).assignTask(taskId, agentIds);

    // Complete
    const creatorBalBefore = await ethers.provider.getBalance(creator.address);
    const tx = await router.connect(creator).completeTask(taskId, "0x1234");
    await tx.wait();

    const creatorBalAfter = await ethers.provider.getBalance(creator.address);

    // Payout = reward - 1% fee = 0.99 ETH
    expect(creatorBalAfter - creatorBalBefore).to.be.closeTo(
      reward - reward / 100n,
      ethers.parseEther("0.01")
    );

    // Task should be completed
    const task = await router.tasks(taskId);
    expect(task.status).to.equal(2); // Completed
  });

  it("cancel task refunds full reward", async function () {
    const reward = ethers.parseEther("0.5");

    const tx = await router.connect(creator).createTask(
      "Cancel test",
      Math.floor(Date.now() / 1000) + 86400,
      { value: reward }
    );
    const receipt = await tx.wait();
    const taskId = receipt.logs.find(
      (l) => l.fragment && l.fragment.name === "TaskCreated"
    ).args.taskId;

    expect(await ethers.provider.getBalance(await router.getAddress()))
      .to.equal(reward);

    const creatorBalBefore = await ethers.provider.getBalance(creator.address);
    await router.connect(creator).cancelTask(taskId);
    const creatorBalAfter = await ethers.provider.getBalance(creator.address);

    expect(creatorBalAfter - creatorBalBefore).to.be.closeTo(reward, ethers.parseEther("0.01"));
    expect(await ethers.provider.getBalance(await router.getAddress())).to.equal(0n);
  });
});
