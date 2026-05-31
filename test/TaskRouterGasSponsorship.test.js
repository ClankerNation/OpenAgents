const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter Gas Sponsorship", function () {
  let taskRouter, agentRegistry;
  let owner, agent, relayer;

  beforeEach(async function () {
    [owner, agent, relayer] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    agentRegistry = await AgentRegistry.deploy(0);
    await agentRegistry.waitForDeployment();

    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    taskRouter = await TaskRouter.deploy(await agentRegistry.getAddress(), 250);
    await taskRouter.waitForDeployment();
  });

  describe("Gas Deposit Management", function () {
    it("should accept gas deposits", async function () {
      await taskRouter.connect(agent).depositGas({ value: ethers.parseEther("1.0") });
      expect(await taskRouter.gasDeposits(agent.address)).to.equal(ethers.parseEther("1.0"));
    });

    it("should allow gas withdrawal", async function () {
      await taskRouter.connect(agent).depositGas({ value: ethers.parseEther("1.0") });
      await taskRouter.connect(agent).withdrawGas(ethers.parseEther("0.5"));
      expect(await taskRouter.gasDeposits(agent.address)).to.equal(ethers.parseEther("0.5"));
    });

    it("should reject withdrawal exceeding deposit", async function () {
      await expect(
        taskRouter.connect(agent).withdrawGas(ethers.parseEther("1.0"))
      ).to.be.revertedWith("Insufficient gas deposit");
    });
  });

  describe("Nonce Tracking", function () {
    it("should start at zero for new agents", async function () {
      expect(await taskRouter.nonces(agent.address)).to.equal(0);
    });
  });
});
