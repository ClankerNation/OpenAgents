const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter", function () {
  let taskRouter, agentRegistry, rewardToken;
  let owner, creator, agentOwner;
  let agentId;

  before(async function () {
    [owner, creator, agentOwner] = await ethers.getSigners();

    // 1. Deploy AgentRegistry
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    agentRegistry = await AgentRegistry.deploy(0); // 0 registration fee
    await agentRegistry.waitForDeployment();

    // 2. Register an Agent
    const tx = await agentRegistry.connect(agentOwner).registerAgent("Test Agent", "http://test.com");
    const receipt = await tx.wait();
    
    // In ethers v6, we parse logs
    const event = receipt.logs.find(log => log.eventName === 'AgentRegistered' || (log.fragment && log.fragment.name === 'AgentRegistered'));
    agentId = event.args[0]; // First arg is agentId

    // 3. Deploy MockNonRevertingERC20
    const MockToken = await ethers.getContractFactory("MockNonRevertingERC20");
    rewardToken = await MockToken.deploy();
    await rewardToken.waitForDeployment();

    // 4. Deploy TaskRouter with platformFee of 10% (1000 basis points)
    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    taskRouter = await TaskRouter.deploy(agentRegistry.target, 1000, rewardToken.target);
    await taskRouter.waitForDeployment();

    // Mint tokens to the task creator
    await rewardToken.mint(creator.address, ethers.parseEther("1000"));
  });

  it("should revert completeTask if the underlying token transfer fails (without reverting) due to SafeERC20", async function () {
    const rewardAmount = ethers.parseEther("100");
    
    // Creator approves and creates a task
    await rewardToken.connect(creator).approve(taskRouter.target, rewardAmount);
    await taskRouter.connect(creator).createTask("Fix a bug", 1999999999, rewardAmount);

    // Agent owner assigns the task to themselves
    await taskRouter.connect(agentOwner).assignTask(0, agentId);

    // Mock token is set to fail the next transfer silently (returning false)
    await rewardToken.setFailNextTransfer(true);

    // Agent owner tries to complete the task, SafeERC20 should intercept the false return and revert
    await expect(
      taskRouter.connect(agentOwner).completeTask(0, "0x")
    ).to.be.reverted;
  });

  describe("Fee Withdrawal", function () {
    let taskId;
    let rewardAmount;

    beforeEach(async function () {
      await rewardToken.setFailNextTransfer(false);
      rewardAmount = ethers.parseEther("100");
      // Approve and create a task
      await rewardToken.connect(creator).approve(taskRouter.target, rewardAmount);
      const tx = await taskRouter.connect(creator).createTask("Another task", 1999999999, rewardAmount);
      const receipt = await tx.wait();
      
      const event = receipt.logs.find(log => log.eventName === 'TaskCreated' || (log.fragment && log.fragment.name === 'TaskCreated'));
      taskId = event.args[0];
      
      // Assign the task
      await taskRouter.connect(agentOwner).assignTask(taskId, agentId);
    });

    it("should accrue fees correctly upon task completion", async function () {
      const initialFees = await taskRouter.accumulatedFees();
      
      // Ensure the mock token doesn't fail
      await rewardToken.setFailNextTransfer(false);

      // Complete the task
      await taskRouter.connect(agentOwner).completeTask(taskId, "0x");

      // Fee is 10% (1000 basis points) of 100 = 10
      const expectedFee = ethers.parseEther("10");
      const finalFees = await taskRouter.accumulatedFees();

      expect(finalFees - initialFees).to.equal(expectedFee);
      taskId++;
    });

    it("should allow the owner to withdraw fees", async function () {
      const feesToWithdraw = await taskRouter.accumulatedFees();
      expect(feesToWithdraw).to.be.gt(0);

      const ownerBalanceBefore = await rewardToken.balanceOf(owner.address);

      // Withdraw fees
      await taskRouter.connect(owner).withdrawFees(owner.address);

      const ownerBalanceAfter = await rewardToken.balanceOf(owner.address);
      const remainingFees = await taskRouter.accumulatedFees();

      expect(ownerBalanceAfter - ownerBalanceBefore).to.equal(feesToWithdraw);
      expect(remainingFees).to.equal(0);
    });

    it("should revert if a non-owner tries to withdraw fees", async function () {
      // Creator is not the owner
      await expect(
        taskRouter.connect(creator).withdrawFees(creator.address)
      ).to.be.revertedWithCustomError(taskRouter, "OwnableUnauthorizedAccount")
       .withArgs(creator.address);
    });
  });
});
