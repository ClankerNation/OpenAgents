const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter #181 — SafeERC20 v2 Upgrade", function () {
  let router, registry, mockToken, owner, agent, user;
  const PLATFORM_FEE = 500;

  beforeEach(async function () {
    [owner, agent, user] = await ethers.getSigners();

    const Reg = await ethers.getContractFactory("AgentRegistry");
    registry = await Reg.deploy(0);
    await registry.waitForDeployment();

    const MockToken = await ethers.getContractFactory("MockERC20");
    mockToken = await MockToken.deploy("Mock", "MCK", 18);
    await mockToken.waitForDeployment();

    const Router = await ethers.getContractFactory("TaskRouter");
    router = await Router.deploy(await registry.getAddress(), PLATFORM_FEE);
    await router.waitForDeployment();
  });

  describe("ETH flow", function () {
    it("should create and complete a task with ETH", async function () {
      await registry.connect(agent).registerAgent("TestAgent", "ipfs://meta");
      const agentId = await registry.agentIds(0);
      const deadline = (await ethers.provider.getBlock("latest")).timestamp + 86400;

      await router.createTask("Test task", deadline, { value: ethers.parseEther("1") });
      await router.connect(agent).assignTask(0, agentId);
      await router.connect(agent).completeTask(0, "0x");

      const task = await router.tasks(0);
      expect(task.status).to.equal(3);
    });

    it("should cancel and refund ETH", async function () {
      const deadline = (await ethers.provider.getBlock("latest")).timestamp + 86400;
      await router.createTask("Cancel test", deadline, { value: ethers.parseEther("0.5") });
      await router.cancelTask(0);
      const task = await router.tasks(0);
      expect(task.status).to.equal(4);
    });
  });

  describe("ERC20 flow with SafeERC20", function () {
    beforeEach(async function () {
      await router.setPaymentToken(await mockToken.getAddress());
      await mockToken.mint(owner.address, ethers.parseEther("1000"));
      await mockToken.connect(owner).approve(await router.getAddress(), ethers.parseEther("1000"));
      await registry.connect(agent).registerAgent("TestAgent", "ipfs://meta");
    });

    it("should create task with ERC20 tokens", async function () {
      const agentId = await registry.agentIds(0);
      const deadline = (await ethers.provider.getBlock("latest")).timestamp + 86400;

      await router.connect(owner).createTask("ERC20 task", deadline, {
        value: ethers.parseEther("10"),
      });

      await router.connect(agent).assignTask(0, agentId);
      const task = await router.tasks(0);
      expect(task.status).to.equal(1);
    });

    it("should complete task and payout via safeTransfer", async function () {
      const agentId = await registry.agentIds(0);
      const deadline = (await ethers.provider.getBlock("latest")).timestamp + 86400;

      await router.connect(owner).createTask("ERC20 task", deadline, {
        value: ethers.parseEther("10"),
      });

      await router.connect(agent).assignTask(0, agentId);
      const balBefore = await mockToken.balanceOf(agent.address);
      await router.connect(agent).completeTask(0, "0x");
      const balAfter = await mockToken.balanceOf(agent.address);

      expect(balAfter - balBefore).to.equal(ethers.parseEther("9.5"));
      const task = await router.tasks(0);
      expect(task.status).to.equal(3);
    });

    it("should revert on failed transfer with mock non-reverting token", async function () {
      const NonReverting = await ethers.getContractFactory("NonRevertingERC20");
      const nonRev = await NonReverting.deploy("NonRev", "NRV", 18);
      await nonRev.waitForDeployment();

      await router.setPaymentToken(await nonRev.getAddress());
      await nonRev.mint(owner.address, ethers.parseEther("100"));
      await nonRev.connect(owner).approve(await router.getAddress(), ethers.parseEther("100"));

      const agentId = await registry.agentIds(0);
      const deadline = (await ethers.provider.getBlock("latest")).timestamp + 86400;

      await router.connect(owner).createTask("NonRev task", deadline, {
        value: ethers.parseEther("10"),
      });

      await router.connect(agent).assignTask(0, agentId);
      await nonRev.connect(owner).transfer(agent.address, await nonRev.balanceOf(owner.address));

      await expect(
        router.connect(agent).completeTask(0, "0x")
      ).to.be.revertedWith("SafeERC20: ERC20 operation did not succeed");
    });
  });

  describe("withdrawFees", function () {
    it("should withdraw ETH fees", async function () {
      const deadline = (await ethers.provider.getBlock("latest")).timestamp + 86400;
      await router.createTask("Fee test", deadline, { value: ethers.parseEther("1") });

      const balBefore = await ethers.provider.getBalance(user.address);
      await router.withdrawFees(user.address);
      const balAfter = await ethers.provider.getBalance(user.address);
      expect(balAfter > balBefore).to.be.true;
    });

    it("should withdraw ERC20 fees", async function () {
      await router.setPaymentToken(await mockToken.getAddress());
      await mockToken.mint(owner.address, ethers.parseEther("100"));
      await mockToken.connect(owner).approve(await router.getAddress(), ethers.parseEther("100"));

      const deadline = (await ethers.provider.getBlock("latest")).timestamp + 86400;
      await router.connect(owner).createTask("Fee token test", deadline, {
        value: ethers.parseEther("10"),
      });

      const balBefore = await mockToken.balanceOf(user.address);
      await router.withdrawFees(user.address);
      const balAfter = await mockToken.balanceOf(user.address);
      expect(balAfter > balBefore).to.be.true;
    });
  });
});
