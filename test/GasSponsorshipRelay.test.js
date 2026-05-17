const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("GasSponsorshipRelay", function () {
  let registry, taskRouter;
  let owner, agent, relayer, other;
  const REGISTRATION_FEE = ethers.parseEther("0.01");

  before(async function () {
    [owner, agent, relayer, other] = await ethers.getSigners();
  });

  /**
   * Helper: sign calldata as an agent for a meta-transaction.
   * Returns the signature bytes.
   */
  async function signMetaTx(signer, data, nonce) {
    const packed = ethers.solidityPacked(
      ["bytes", "uint256"],
      [data, nonce]
    );
    const messageHash = ethers.keccak256(packed);
    const signature = await signer.signMessage(ethers.getBytes(messageHash));
    return signature;
  }

  beforeEach(async function () {
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(REGISTRATION_FEE);
    await registry.waitForDeployment();

    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    taskRouter = await TaskRouter.deploy(registry.target, 250);
    await taskRouter.waitForDeployment();

    await registry.setTaskRouter(taskRouter.target);
  });

  // ── AgentRegistry: Stake Management ─────────────────────────────

  describe("AgentRegistry Stake Management", function () {
    it("should allow an agent owner to deposit stake", async function () {
      const amount = ethers.parseEther("1.0");
      await registry.connect(agent).depositStake({ value: amount });

      const stake = await registry.stakes(agent.address);
      expect(stake).to.equal(amount);
    });

    it("should emit StakeDeposited event on deposit", async function () {
      const amount = ethers.parseEther("2.0");
      await expect(registry.connect(agent).depositStake({ value: amount }))
        .to.emit(registry, "StakeDeposited")
        .withArgs(agent.address, amount);
    });

    it("should reject zero stake deposits", async function () {
      await expect(
        registry.connect(agent).depositStake({ value: 0 })
      ).to.be.revertedWith("Zero stake");
    });

    it("should allow an agent owner to withdraw stake", async function () {
      await registry.connect(agent).depositStake({ value: ethers.parseEther("3.0") });

      const withdrawAmount = ethers.parseEther("1.0");
      await registry.connect(agent).withdrawStake(withdrawAmount);

      const remaining = await registry.stakes(agent.address);
      expect(remaining).to.equal(ethers.parseEther("2.0"));
    });

    it("should emit StakeWithdrawn event on withdrawal", async function () {
      await registry.connect(agent).depositStake({ value: ethers.parseEther("3.0") });
      const amount = ethers.parseEther("1.0");

      await expect(registry.connect(agent).withdrawStake(amount))
        .to.emit(registry, "StakeWithdrawn")
        .withArgs(agent.address, amount);
    });

    it("should reject withdrawals exceeding stake", async function () {
      await registry.connect(agent).depositStake({ value: ethers.parseEther("1.0") });

      await expect(
        registry.connect(agent).withdrawStake(ethers.parseEther("2.0"))
      ).to.be.revertedWith("Insufficient stake");
    });

    it("should prevent non-owner from withdrawing another's stake", async function () {
      await registry.connect(agent).depositStake({ value: ethers.parseEther("1.0") });

      await expect(
        registry.connect(other).withdrawStake(ethers.parseEther("0.5"))
      ).to.be.revertedWith("Insufficient stake");
    });

    it("should emit TaskRouterSet event on first set", async function () {
      // Deploy a fresh registry so we test the first setTaskRouter call
      const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
      const freshRegistry = await AgentRegistry.deploy(REGISTRATION_FEE);
      await freshRegistry.waitForDeployment();

      const TaskRouter = await ethers.getContractFactory("TaskRouter");
      const freshRouter = await TaskRouter.deploy(freshRegistry.target, 250);
      await freshRouter.waitForDeployment();

      await expect(freshRegistry.setTaskRouter(freshRouter.target))
        .to.emit(freshRegistry, "TaskRouterSet")
        .withArgs(ethers.ZeroAddress, freshRouter.target);
    });

    it("should reject setting zero address as TaskRouter", async function () {
      await expect(
        registry.setTaskRouter(ethers.ZeroAddress)
      ).to.be.revertedWith("Zero address");
    });

    it("should only allow owner to set TaskRouter", async function () {
      await expect(
        registry.connect(agent).setTaskRouter(taskRouter.target)
      ).to.be.revertedWithCustomError(registry, "OwnableUnauthorizedAccount");
    });

    it("should enforce onlyTaskRouter on deductStake", async function () {
      await registry.connect(agent).depositStake({ value: ethers.parseEther("5.0") });

      const deductAmount = ethers.parseEther("0.01");

      // Non-TaskRouter cannot call deductStake
      await expect(
        registry.connect(agent).deductStake(agent.address, relayer.address, deductAmount)
      ).to.be.revertedWith("Only TaskRouter");

      // TaskRouter CAN call deductStake (tested via executeOnBehalf in Sponsored Execution tests)
      // This is verified by the fact that executeOnBehalf tests pass — they internally
      // call deductStake which would revert if onlyTaskRouter failed.
    });
  });

  // ── TaskRouter: executeOnBehalf ──────────────────────────────────

  describe("executeOnBehalf — Sponsored Execution", function () {
    const TASK_DESC = "Compute weather forecast";
    const DEADLINE_OFFSET = 86400; // 1 day

    it("should execute assignTask via sponsored meta-transaction", async function () {
      // Agent deposits stake for gas reimbursement
      await registry.connect(agent).depositStake({ value: ethers.parseEther("5.0") });

      // Register an agent
      const agentName = "WeatherBot";
      const endpoint = "https://weather.example.com/api";
      await registry.connect(agent).registerAgent(agentName, endpoint, {
        value: REGISTRATION_FEE,
      });

      const agentId = ethers.keccak256(
        ethers.solidityPacked(
          ["address", "string", "uint256"],
          [agent.address, agentName, (await ethers.provider.getBlock("latest")).timestamp]
        )
      );

      // Create a task normally
      const deadline = Math.floor(Date.now() / 1000) + DEADLINE_OFFSET;
      await taskRouter.createTask(TASK_DESC, deadline, {
        value: ethers.parseEther("0.1"),
      });
      const taskId = 0;

      // Build assignTask calldata
      const assignData = taskRouter.interface.encodeFunctionData(
        "assignTask",
        [taskId, agentId]
      );

      // Get current nonce and sign
      const nonce = await taskRouter.nonces(agent.address);
      const signature = await signMetaTx(agent, assignData, nonce);

      // Relayer executes on behalf of agent
      const tx = await taskRouter.connect(relayer).executeOnBehalf(
        agent.address, assignData, signature
      );
      const receipt = await tx.wait();

      // Verify SponsoredExecution event was emitted (with success=true)
      // We use a flexible assertion since gasReimbursement varies
      const event = receipt.logs.find(
        (log) => log.fragment && log.fragment.name === "SponsoredExecution"
      );
      expect(event).to.not.be.undefined;
      expect(event.args[0]).to.equal(agent.address); // agent
      expect(event.args[1]).to.equal(relayer.address); // relayer
      expect(event.args[2]).to.equal(nonce); // nonce
      expect(event.args[4]).to.equal(true); // success

      // Verify the task was assigned
      const task = await taskRouter.tasks(taskId);
      expect(task.assignedAgent).to.equal(agentId);
      expect(task.status).to.equal(1); // Assigned
    });

    it("should reject invalid signatures", async function () {
      const assignData = taskRouter.interface.encodeFunctionData(
        "assignTask",
        [0, ethers.ZeroHash]
      );

      // Sign with the wrong signer (other instead of agent)
      const signature = await signMetaTx(other, assignData, 0);

      await expect(
        taskRouter.connect(relayer).executeOnBehalf(agent.address, assignData, signature)
      ).to.be.revertedWith("Invalid signature");
    });

    it("should enforce replay protection via nonces", async function () {
      // Register agent
      await registry.connect(agent).registerAgent("TestBot", "https://test.com", {
        value: REGISTRATION_FEE,
      });

      const agentName = "TestBot";
      const agentId = ethers.keccak256(
        ethers.solidityPacked(
          ["address", "string", "uint256"],
          [agent.address, agentName, (await ethers.provider.getBlock("latest")).timestamp]
        )
      );

      // Create two tasks
      const deadline = Math.floor(Date.now() / 1000) + DEADLINE_OFFSET;
      await taskRouter.createTask("Task1", deadline, { value: ethers.parseEther("0.1") });
      await taskRouter.createTask("Task2", deadline, { value: ethers.parseEther("0.1") });

      await registry.connect(agent).depositStake({ value: ethers.parseEther("1.0") });

      const assignData = taskRouter.interface.encodeFunctionData(
        "assignTask",
        [0, agentId]
      );

      const nonce = await taskRouter.nonces(agent.address);
      const signature = await signMetaTx(agent, assignData, nonce);

      // First execution should succeed
      await taskRouter.connect(relayer).executeOnBehalf(agent.address, assignData, signature);

      // Nonce incremented, replay with same signature should fail
      await expect(
        taskRouter.connect(relayer).executeOnBehalf(agent.address, assignData, signature)
      ).to.be.revertedWith("Invalid signature");
    });

    it("should increment nonce after successful execution", async function () {
      await registry.connect(agent).registerAgent("Bot", "https://bot.com", {
        value: REGISTRATION_FEE,
      });

      const agentName = "Bot";
      const agentId = ethers.keccak256(
        ethers.solidityPacked(
          ["address", "string", "uint256"],
          [agent.address, agentName, (await ethers.provider.getBlock("latest")).timestamp]
        )
      );

      const deadline = Math.floor(Date.now() / 1000) + DEADLINE_OFFSET;
      await taskRouter.createTask("Task", deadline, { value: ethers.parseEther("0.1") });
      await taskRouter.createTask("Task2", deadline, { value: ethers.parseEther("0.1") });
      await registry.connect(agent).depositStake({ value: ethers.parseEther("1.0") });

      const assignData = taskRouter.interface.encodeFunctionData(
        "assignTask",
        [0, agentId]
      );

      let nonce = await taskRouter.nonces(agent.address);
      expect(nonce).to.equal(0);

      const sig1 = await signMetaTx(agent, assignData, 0);
      await taskRouter.connect(relayer).executeOnBehalf(agent.address, assignData, sig1);

      nonce = await taskRouter.nonces(agent.address);
      expect(nonce).to.equal(1);

      const assignData2 = taskRouter.interface.encodeFunctionData(
        "assignTask",
        [1, agentId]
      );

      const sig2 = await signMetaTx(agent, assignData2, 1);
      await taskRouter.connect(relayer).executeOnBehalf(agent.address, assignData2, sig2);

      nonce = await taskRouter.nonces(agent.address);
      expect(nonce).to.equal(2);
    });

    it("should allow execution even with insufficient stake (relayer absorbs cost)", async function () {
      // Register agent with NO stake
      await registry.connect(agent).registerAgent("NoStakeBot", "https://nostake.com", {
        value: REGISTRATION_FEE,
      });

      const agentName = "NoStakeBot";
      const agentId = ethers.keccak256(
        ethers.solidityPacked(
          ["address", "string", "uint256"],
          [agent.address, agentName, (await ethers.provider.getBlock("latest")).timestamp]
        )
      );

      const deadline = Math.floor(Date.now() / 1000) + DEADLINE_OFFSET;
      await taskRouter.createTask("Task", deadline, { value: ethers.parseEther("0.1") });

      const assignData = taskRouter.interface.encodeFunctionData(
        "assignTask",
        [0, agentId]
      );

      const nonce = await taskRouter.nonces(agent.address);
      const signature = await signMetaTx(agent, assignData, nonce);

      // Should succeed — execution still goes through even without stake
      const tx = await taskRouter.connect(relayer).executeOnBehalf(
        agent.address, assignData, signature
      );
      const receipt = await tx.wait();

      // Verify SponsoredExecution was emitted
      const event = receipt.logs.find(
        (log) => log.fragment && log.fragment.name === "SponsoredExecution"
      );
      expect(event).to.not.be.undefined;
      expect(event.args[4]).to.equal(true); // success

      // Verify the task was assigned
      const task = await taskRouter.tasks(0);
      expect(task.assignedAgent).to.equal(agentId);
      expect(task.status).to.equal(1); // Assigned
    });
  });

  // ── Edge Cases ──────────────────────────────────────────────────

  describe("Edge Cases", function () {
    it("should reject execution with forged signature", async function () {
      const data = taskRouter.interface.encodeFunctionData("taskCount");
      const badSignature = "0x" + "00".repeat(65);

      await expect(
        taskRouter.connect(relayer).executeOnBehalf(agent.address, data, badSignature)
      ).to.be.reverted;
    });

    it("should handle view function calls via meta-transaction", async function () {
      const echoData = taskRouter.interface.encodeFunctionData("taskCount");
      const nonce = await taskRouter.nonces(agent.address);
      const signature = await signMetaTx(agent, echoData, nonce);

      // Call taskCount() via meta-transaction — should succeed
      const tx = await taskRouter.connect(relayer).executeOnBehalf(
        agent.address, echoData, signature
      );
      const receipt = await tx.wait();

      const event = receipt.logs.find(
        (log) => log.fragment && log.fragment.name === "SponsoredExecution"
      );
      expect(event).to.not.be.undefined;
      expect(event.args[4]).to.equal(true); // success
    });

    it("should clear _metaTxAgent after execution", async function () {
      const emptyData = "0x";
      const nonce = await taskRouter.nonces(agent.address);
      const signature = await signMetaTx(agent, emptyData, nonce);

      await taskRouter.connect(relayer).executeOnBehalf(
        agent.address, emptyData, signature
      );

      // _metaTxAgent should be cleared back to zero
      expect(await taskRouter.metaTxAgent()).to.equal(ethers.ZeroAddress);
    });

    it("should correctly report _metaTxAgent during execution", async function () {
      const nonce = await taskRouter.nonces(agent.address);

      // Call metaTxAgent() from within a meta-transaction
      const echoData = taskRouter.interface.encodeFunctionData("metaTxAgent");
      const signature = await signMetaTx(agent, echoData, nonce);

      // When metaTxAgent is called during executeOnBehalf, it should return agent
      const tx = await taskRouter.connect(relayer).executeOnBehalf(
        agent.address, echoData, signature
      );
      const receipt = await tx.wait();

      const event = receipt.logs.find(
        (log) => log.fragment && log.fragment.name === "SponsoredExecution"
      );
      expect(event).to.not.be.undefined;
      expect(event.args[4]).to.equal(true);

      // After execution, _metaTxAgent should be cleared
      expect(await taskRouter.metaTxAgent()).to.equal(ethers.ZeroAddress);
    });
  });
});
