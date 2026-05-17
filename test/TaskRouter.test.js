const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter (SafeERC20 v2)", function () {
  let TaskRouter, taskRouter;
  let AgentRegistry, registry;
  let MockNonRevertingERC20, rewardToken;
  let owner, creator, agent1, agent2, feeRecipient;
  const PLATFORM_FEE = 200; // 2% in basis points
  const TASK_REWARD = ethers.parseEther("100");

  before(async function () {
    [owner, creator, agent1, agent2, feeRecipient] = await ethers.getSigners();

    // Deploy AgentRegistry
    AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy();
    await registry.waitForDeployment();

    // Register an agent for testing
    await registry.connect(agent1).registerAgent("agent-alpha", "http://agent1:8080/api");
    await registry.connect(agent2).registerAgent("agent-beta", "http://agent2:8080/api");
  });

  async function deployWithToken(tokenFactory, tokenArgs) {
    const Token = await ethers.getContractFactory(tokenFactory);
    rewardToken = await Token.deploy(...tokenArgs);
    await rewardToken.waitForDeployment();

    TaskRouter = await ethers.getContractFactory("TaskRouter");
    taskRouter = await TaskRouter.deploy(
      await registry.getAddress(),
      await rewardToken.getAddress(),
      PLATFORM_FEE
    );
    await taskRouter.waitForDeployment();

    // Fund creators with tokens
    const supply = ethers.parseEther("1000000");
    if (tokenFactory === "MockNonRevertingERC20") {
      await rewardToken.transfer(creator.address, supply);
    }
  }

  describe("with standard ERC20 (MockNonRevertingERC20 in normal mode)", function () {
    beforeEach(async function () {
      await deployWithToken("MockNonRevertingERC20", ["RewardToken", "RWRD", ethers.parseEther("1000000")]);
      await rewardToken.transfer(creator.address, ethers.parseEther("10000"));
    });

    it("should create a task with ERC20 reward via safeTransferFrom", async function () {
      await rewardToken.connect(creator).approve(await taskRouter.getAddress(), TASK_REWARD);

      const tx = await taskRouter.connect(creator).createTask(
        "Build landing page",
        TASK_REWARD,
        Math.floor(Date.now() / 1000) + 86400
      );

      await expect(tx).to.emit(taskRouter, "TaskCreated").withArgs(0, creator.address, TASK_REWARD);

      const task = await taskRouter.tasks(0);
      expect(task.creator).to.equal(creator.address);
      expect(task.reward).to.equal(TASK_REWARD);
      expect(task.status).to.equal(0); // Open

      // Verify token transfer from creator to contract
      expect(await rewardToken.balanceOf(await taskRouter.getAddress())).to.equal(TASK_REWARD);
    });

    it("should complete a task and pay agent via safeTransfer", async function () {
      await rewardToken.connect(creator).approve(await taskRouter.getAddress(), TASK_REWARD);
      await taskRouter.connect(creator).createTask("Test task", TASK_REWARD, Math.floor(Date.now() / 1000) + 86400);
      await taskRouter.connect(agent1).assignTask(0, ethers.encodeBytes32String("agent-alpha"));

      const agentBalanceBefore = await rewardToken.balanceOf(agent1.address);
      await taskRouter.connect(agent1).completeTask(0, ethers.toUtf8Bytes("task result"));

      const task = await taskRouter.tasks(0);
      expect(task.status).to.equal(2); // Completed

      // Agent received payout (reward - fee)
      const fee = TASK_REWARD * BigInt(PLATFORM_FEE) / 10000n;
      const payout = TASK_REWARD - fee;
      expect(await rewardToken.balanceOf(agent1.address)).to.equal(agentBalanceBefore + payout);
      expect(await taskRouter.accumulatedFees()).to.equal(fee);
    });

    it("should cancel a task and refund via safeTransfer", async function () {
      await rewardToken.connect(creator).approve(await taskRouter.getAddress(), TASK_REWARD);
      await taskRouter.connect(creator).createTask("Test task", TASK_REWARD, Math.floor(Date.now() / 1000) + 86400);

      const creatorBalanceBefore = await rewardToken.balanceOf(creator.address);
      await taskRouter.connect(creator).cancelTask(0);

      const task = await taskRouter.tasks(0);
      expect(task.status).to.equal(4); // Cancelled
      expect(await rewardToken.balanceOf(creator.address)).to.equal(creatorBalanceBefore + TASK_REWARD);
    });

    it("should allow owner to withdraw accumulated fees", async function () {
      await rewardToken.connect(creator).approve(await taskRouter.getAddress(), TASK_REWARD);
      await taskRouter.connect(creator).createTask("Test", TASK_REWARD, Math.floor(Date.now() / 1000) + 86400);
      await taskRouter.connect(agent1).assignTask(0, ethers.encodeBytes32String("agent-alpha"));
      await taskRouter.connect(agent1).completeTask(0, ethers.toUtf8Bytes("done"));

      const fee = TASK_REWARD * BigInt(PLATFORM_FEE) / 10000n;
      expect(await taskRouter.accumulatedFees()).to.equal(fee);

      const feeBalBefore = await rewardToken.balanceOf(feeRecipient.address);
      await expect(taskRouter.connect(owner).withdrawFees(feeRecipient.address))
        .to.emit(taskRouter, "FeesWithdrawn")
        .withArgs(feeRecipient.address, fee);

      expect(await rewardToken.balanceOf(feeRecipient.address)).to.equal(feeBalBefore + fee);
      expect(await taskRouter.accumulatedFees()).to.equal(0);
    });

    it("should revert if non-owner tries to withdraw fees", async function () {
      await rewardToken.connect(creator).approve(await taskRouter.getAddress(), TASK_REWARD);
      await taskRouter.connect(creator).createTask("Test", TASK_REWARD, Math.floor(Date.now() / 1000) + 86400);
      await taskRouter.connect(agent1).assignTask(0, ethers.encodeBytes32String("agent-alpha"));
      await taskRouter.connect(agent1).completeTask(0, ethers.toUtf8Bytes("done"));

      await expect(
        taskRouter.connect(creator).withdrawFees(creator.address)
      ).to.be.revertedWith("Not owner");
    });
  });

  describe("with non-reverting ERC20 (shouldFail = true)", function () {
    beforeEach(async function () {
      await deployWithToken("MockNonRevertingERC20", ["FakeToken", "FAKE", ethers.parseEther("1000000")]);
      await rewardToken.transfer(creator.address, ethers.parseEther("10000"));
    });

    it("should revert createTask when transferFrom returns false", async function () {
      await rewardToken.connect(creator).approve(await taskRouter.getAddress(), TASK_REWARD);
      await rewardToken.setShouldFail(true);

      await expect(
        taskRouter.connect(creator).createTask("Should fail", TASK_REWARD, Math.floor(Date.now() / 1000) + 86400)
      ).to.be.reverted; // SafeERC20 reverts on false return
    });

    it("should revert completeTask when safeTransfer would fail", async function () {
      // Create task successfully first
      await rewardToken.connect(creator).approve(await taskRouter.getAddress(), TASK_REWARD);
      await taskRouter.connect(creator).createTask("Task", TASK_REWARD, Math.floor(Date.now() / 1000) + 86400);
      await taskRouter.connect(agent1).assignTask(0, ethers.encodeBytes32String("agent-alpha"));

      // Now set the token to fail
      await rewardToken.setShouldFail(true);

      await expect(
        taskRouter.connect(agent1).completeTask(0, ethers.toUtf8Bytes("should fail"))
      ).to.be.reverted; // SafeERC20 catches the false return
    });

    it("should revert cancelTask when safeTransfer fails", async function () {
      await rewardToken.connect(creator).approve(await taskRouter.getAddress(), TASK_REWARD);
      await taskRouter.connect(creator).createTask("Task", TASK_REWARD, Math.floor(Date.now() / 1000) + 86400);

      await rewardToken.setShouldFail(true);

      await expect(
        taskRouter.connect(creator).cancelTask(0)
      ).to.be.reverted; // SafeERC20 catches the false return
    });

    it("should not update task state when transfer fails in completeTask", async function () {
      await rewardToken.connect(creator).approve(await taskRouter.getAddress(), TASK_REWARD);
      await taskRouter.connect(creator).createTask("Task", TASK_REWARD, Math.floor(Date.now() / 1000) + 86400);
      await taskRouter.connect(agent1).assignTask(0, ethers.encodeBytes32String("agent-alpha"));

      await rewardToken.setShouldFail(true);

      await expect(
        taskRouter.connect(agent1).completeTask(0, ethers.toUtf8Bytes("should fail"))
      ).to.be.reverted;

      // Task should still be in Assigned state (not Completed) — atomic revert
      const task = await taskRouter.tasks(0);
      expect(task.status).to.equal(1); // Assigned
    });

    it("should not update task state when transfer fails in cancelTask", async function () {
      await rewardToken.connect(creator).approve(await taskRouter.getAddress(), TASK_REWARD);
      await taskRouter.connect(creator).createTask("Task", TASK_REWARD, Math.floor(Date.now() / 1000) + 86400);

      await rewardToken.setShouldFail(true);

      await expect(
        taskRouter.connect(creator).cancelTask(0)
      ).to.be.reverted;

      // Task should still be Open (not Cancelled)
      const task = await taskRouter.tasks(0);
      expect(task.status).to.equal(0); // Open
    });
  });

  describe("constructor validation", function () {
    it("should revert with zero reward token address", async function () {
      const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
      const reg = await AgentRegistry.deploy();
      await reg.waitForDeployment();

      const TaskRouter = await ethers.getContractFactory("TaskRouter");
      await expect(
        TaskRouter.deploy(await reg.getAddress(), ethers.ZeroAddress, PLATFORM_FEE)
      ).to.be.revertedWith("Invalid reward token");
    });
  });
});
