const { expect } = require("chai");
const { ethers } = require("hardhat");

// Tests for the issue #181 SafeERC20 fix in TaskRouter.
// Mirrors test/TaskRouter.t.sol (Foundry) in the repo's native Hardhat
// framework. Proves balances actually moved, that a `false`-returning
// token reverts the whole transaction, and that the ETH flow is unchanged.
describe("TaskRouter — SafeERC20 fix (#181)", function () {
  const REWARD = ethers.parseEther("1000");
  const FEE = ethers.parseEther("50");
  const PAYOUT = ethers.parseEther("950");
  const FEE_BPS = 500; // 5%
  const STATUS = { Open: 0, Assigned: 1, Completed: 2, Disputed: 3, Cancelled: 4 };

  async function deployFixture() {
    const [admin, creator, agentOwner, stranger] = await ethers.getSigners();
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    const registry = await AgentRegistry.deploy(0);
    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    const router = await TaskRouter.deploy(await registry.getAddress(), FEE_BPS);
    const MockToken = await ethers.getContractFactory("MockToken");
    const token = await MockToken.deploy();

    const tx = await registry.connect(agentOwner).registerAgent("agent-1", "https://example.com");
    const receipt = await tx.wait();
    const parsed = receipt.logs
      .map((l) => {
        try {
          return registry.interface.parseLog(l);
        } catch {
          return null;
        }
      })
      .find((e) => e && e.name === "AgentRegistered");
    const agentId = parsed.args.agentId;
    const deadline = (await ethers.provider.getBlock("latest")).timestamp + 86400;
    return { admin, creator, agentOwner, stranger, registry, router, token, agentId, deadline };
  }

  async function createERC20Task(f, amount = REWARD) {
    await f.token.mint(f.creator.address, amount);
    await f.token.connect(f.creator).approve(await f.router.getAddress(), amount);
    const tx = await f.router
      .connect(f.creator)
      .createTaskERC20("do work", f.deadline, await f.token.getAddress(), amount);
    const receipt = await tx.wait();
    const parsed = receipt.logs
      .map((l) => {
        try {
          return f.router.interface.parseLog(l);
        } catch {
          return null;
        }
      })
      .find((e) => e && e.name === "TaskCreated");
    return parsed.args.taskId;
  }

  it("ERC-20 full flow pays a standard token and tracks the fee", async function () {
    const f = await deployFixture();
    const taskId = await createERC20Task(f);
    expect(await f.token.balanceOf(await f.router.getAddress())).to.equal(REWARD);

    await f.router.connect(f.agentOwner).assignTask(taskId, f.agentId);
    await f.router.connect(f.agentOwner).completeTask(taskId, "0x646f6e65"); // "done"

    expect(await f.token.balanceOf(f.agentOwner.address)).to.equal(PAYOUT);
    expect(await f.token.balanceOf(await f.router.getAddress())).to.equal(FEE);
    expect(await f.router.feesCollected(await f.token.getAddress())).to.equal(FEE);
    expect((await f.router.tasks(taskId)).status).to.equal(STATUS.Completed);
  });

  it("completeTask reverts when the token returns false (no silent payout)", async function () {
    const f = await deployFixture();
    await f.token.setFailTransfer(true);
    const taskId = await createERC20Task(f);
    await f.router.connect(f.agentOwner).assignTask(taskId, f.agentId);

    await expect(
      f.router.connect(f.agentOwner).completeTask(taskId, "0x646f6e65")
    )
      .to.be.revertedWithCustomError(f.router, "SafeERC20FailedOperation")
      .withArgs(await f.token.getAddress());

    expect((await f.router.tasks(taskId)).status).to.equal(STATUS.Assigned);
    expect(await f.token.balanceOf(f.agentOwner.address)).to.equal(0);
    expect(await f.token.balanceOf(await f.router.getAddress())).to.equal(REWARD);
    expect(await f.router.feesCollected(await f.token.getAddress())).to.equal(0);
  });

  it("cancelTask reverts when the token returns false (escrow stays put)", async function () {
    const f = await deployFixture();
    await f.token.setFailTransfer(true);
    const taskId = await createERC20Task(f);

    await expect(f.router.connect(f.creator).cancelTask(taskId))
      .to.be.revertedWithCustomError(f.router, "SafeERC20FailedOperation")
      .withArgs(await f.token.getAddress());

    expect((await f.router.tasks(taskId)).status).to.equal(STATUS.Open);
    expect(await f.token.balanceOf(f.creator.address)).to.equal(0);
    expect(await f.token.balanceOf(await f.router.getAddress())).to.equal(REWARD);
  });

  it("createTaskERC20 reverts when transferFrom returns false", async function () {
    const f = await deployFixture();
    await f.token.setFailTransferFrom(true);
    await f.token.mint(f.creator.address, REWARD);
    await f.token.connect(f.creator).approve(await f.router.getAddress(), REWARD);

    await expect(
      f.router.connect(f.creator).createTaskERC20("do work", f.deadline, await f.token.getAddress(), REWARD)
    )
      .to.be.revertedWithCustomError(f.router, "SafeERC20FailedOperation")
      .withArgs(await f.token.getAddress());

    expect(await f.router.taskCount()).to.equal(0);
    expect(await f.token.balanceOf(await f.router.getAddress())).to.equal(0);
  });

  it("legacy no-return token works end to end via SafeERC20", async function () {
    const f = await deployFixture();
    await f.token.setNoReturn(true);
    const taskId = await createERC20Task(f);
    await f.router.connect(f.agentOwner).assignTask(taskId, f.agentId);

    await f.router.connect(f.agentOwner).completeTask(taskId, "0x646f6e65");

    expect(await f.token.balanceOf(f.agentOwner.address)).to.equal(PAYOUT);
    expect(await f.token.balanceOf(await f.router.getAddress())).to.equal(FEE);
  });

  it("ETH flow is unchanged (regression)", async function () {
    const f = await deployFixture();
    const tx = await f.router
      .connect(f.creator)
      .createTask("do work", f.deadline, { value: ethers.parseEther("1") });
    const receipt = await tx.wait();
    const taskId = receipt.logs
      .map((l) => {
        try {
          return f.router.interface.parseLog(l);
        } catch {
          return null;
        }
      })
      .find((e) => e && e.name === "TaskCreated").args.taskId;

    await f.router.connect(f.agentOwner).assignTask(taskId, f.agentId);
    await expect(() =>
      f.router.connect(f.agentOwner).completeTask(taskId, "0x646f6e65")
    ).to.changeEtherBalance(f.agentOwner, ethers.parseEther("0.95"));

    expect(await f.router.feesCollectedETH()).to.equal(ethers.parseEther("0.05"));
  });

  it("withdrawFees: only the registry owner, and only accrued fees", async function () {
    const f = await deployFixture();
    const taskId = await createERC20Task(f);
    await f.router.connect(f.agentOwner).assignTask(taskId, f.agentId);
    await f.router.connect(f.agentOwner).completeTask(taskId, "0x646f6e65");
    // A second task's escrow must never be withdrawable as "fees".
    await createERC20Task(f);

    await expect(
      f.router.connect(f.stranger).withdrawFees(await f.token.getAddress())
    ).to.be.revertedWith("Not admin");

    await expect(() => f.router.withdrawFees(await f.token.getAddress())).to.changeTokenBalance(
      f.token,
      f.admin,
      FEE
    );
    expect(await f.token.balanceOf(await f.router.getAddress())).to.equal(REWARD);
    expect(await f.router.feesCollected(await f.token.getAddress())).to.equal(0);
    await expect(f.router.withdrawFees(await f.token.getAddress())).to.be.revertedWith("No fees");
  });
});
