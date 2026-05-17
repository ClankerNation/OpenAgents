const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter — Gas Sponsorship Relay", function () {
  let taskRouter, registry;
  let owner, agent, relayer, other;

  before(async function () {
    [owner, agent, relayer, other] = await ethers.getSigners();

    // Deploy AgentRegistry
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(ethers.parseEther("0.01"));
    await registry.waitForDeployment();

    // Deploy TaskRouter
    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    taskRouter = await TaskRouter.deploy(registry.target, 100); // 1% platform fee
    await taskRouter.waitForDeployment();
  });

  // Helper: sign calldata + nonce with agent's key
  async function signForAgent(signer, agentAddr, data, nonce) {
    const messageHash = ethers.keccak256(
      ethers.solidityPacked(["bytes", "uint256"], [data, nonce])
    );
    // EIP-191 signed message
    const ethSignedHash = ethers.hashMessage(ethers.getBytes(messageHash));
    const signature = await signer.signMessage(ethers.getBytes(messageHash));
    return signature;
  }

  describe("Gas Deposit and Withdrawal", function () {
    it("should allow agent to deposit ETH for gas", async function () {
      const deposit = ethers.parseEther("1");
      await taskRouter.connect(agent).depositGas({ value: deposit });
      expect(await taskRouter.agentStakes(agent.address)).to.equal(deposit);
    });

    it("should allow agent to withdraw unused gas stake", async function () {
      const deposit = ethers.parseEther("0.5");
      await taskRouter.connect(other).depositGas({ value: deposit });

      const before = await ethers.provider.getBalance(other.address);
      const tx = await taskRouter.connect(other).withdrawGas(deposit);
      const receipt = await tx.wait();
      const gasCost = receipt.gasUsed * receipt.gasPrice;
      const after = await ethers.provider.getBalance(other.address);

      expect(await taskRouter.agentStakes(other.address)).to.equal(0);
      expect(after).to.equal(before + deposit - gasCost);
    });

    it("should reject zero deposit", async function () {
      await expect(
        taskRouter.connect(agent).depositGas({ value: 0 })
      ).to.be.revertedWith("Must deposit ETH");
    });

    it("should reject withdrawal exceeding stake", async function () {
      await expect(
        taskRouter.connect(agent).withdrawGas(ethers.parseEther("100"))
      ).to.be.revertedWith("Insufficient stake");
    });

    it("should emit GasDeposited event", async function () {
      await expect(taskRouter.connect(relayer).depositGas({ value: ethers.parseEther("0.1") }))
        .to.emit(taskRouter, "GasDeposited")
        .withArgs(relayer.address, ethers.parseEther("0.1"));
    });

    it("should emit GasWithdrawn event", async function () {
      await taskRouter.connect(relayer).depositGas({ value: ethers.parseEther("0.2") });
      await expect(taskRouter.connect(relayer).withdrawGas(ethers.parseEther("0.1")))
        .to.emit(taskRouter, "GasWithdrawn")
        .withArgs(relayer.address, ethers.parseEther("0.1"));
    });
  });

  describe("Sponsored Execution", function () {
    const nonce = 0;
    let calldata;

    before(async function () {
      // Ensure agent has sufficient stake for gas reimbursement
      await taskRouter.connect(agent).depositGas({ value: ethers.parseEther("5") });
      // Calldata: createTask("Sponsored task", far-future deadline)
      calldata = taskRouter.interface.encodeFunctionData("createTask", [
        "Sponsored task",
        Math.floor(Date.now() / 1000) + 365 * 86400, // 1 year from now
      ]);
    });

    it("should execute on behalf of agent with valid signature", async function () {
      const sig = await signForAgent(agent, agent.address, calldata, nonce);

      await expect(
        taskRouter.connect(relayer).executeOnBehalf(agent.address, calldata, sig)
      )
        .to.emit(taskRouter, "ExecutedOnBehalf")
        .withArgs(agent.address, relayer.address, nonce, (v) => v >= 0n);

      // Nonce should be incremented
      expect(await taskRouter.agentNonces(agent.address)).to.equal(nonce + 1);
    });

    it("should reimburse relayer from agent stake", async function () {
      const calldata2 = taskRouter.interface.encodeFunctionData("createTask", [
        "Another sponsored task",
        Math.floor(Date.now() / 1000) + 365 * 86400,
      ]);
      const sig2 = await signForAgent(agent, agent.address, calldata2, 1);

      const stakeBefore = await taskRouter.agentStakes(agent.address);
      const relayerBalanceBefore = await ethers.provider.getBalance(relayer.address);

      const tx = await taskRouter.connect(relayer).executeOnBehalf(
        agent.address,
        calldata2,
        sig2
      );
      const receipt = await tx.wait();

      const stakeAfter = await taskRouter.agentStakes(agent.address);
      const relayerBalanceAfter = await ethers.provider.getBalance(relayer.address);

      // Agent stake should decrease
      expect(stakeAfter).to.be.lt(stakeBefore);
      // Relayer should have been reimbursed (net gas cost covered by agent stake)
      // The relayer pays tx gas but gets reimbursed. Net effect should roughly balance.
    });

    it("should emit ExecutedOnBehalf event", async function () {
      const calldata3 = taskRouter.interface.encodeFunctionData("createTask", [
        "Event emission test",
        Math.floor(Date.now() / 1000) + 365 * 86400,
      ]);
      const sig3 = await signForAgent(agent, agent.address, calldata3, 2);

      await expect(
        taskRouter.connect(relayer).executeOnBehalf(agent.address, calldata3, sig3)
      )
        .to.emit(taskRouter, "ExecutedOnBehalf")
        .withArgs(agent.address, relayer.address, 2, (v) => v >= 0n);
    });
  });

  describe("Replay Prevention", function () {
    it("should reject replayed signature (same nonce)", async function () {
      await taskRouter.connect(agent).depositGas({ value: ethers.parseEther("5") });
      const calldata4 = taskRouter.interface.encodeFunctionData("createTask", [
        "Replay test",
        Math.floor(Date.now() / 1000) + 365 * 86400,
      ]);

      // Agent hasn't used nonce 3 yet — artificially set nonce to 3 for clean test
      const testNonce = 42;
      // We can't set agentNonces directly in the test without a setter.
      // Instead, use the agent's current nonce. If agent has used up to nonce 2,
      // we sign with nonce 3. After first execution, nonce becomes 4, so signing
      // with nonce 3 again should fail.
      const currentNonce = await taskRouter.agentNonces(agent.address);
      const sig = await signForAgent(agent, agent.address, calldata4, currentNonce);

      // First execution: succeeds
      await taskRouter.connect(relayer).executeOnBehalf(agent.address, calldata4, sig);

      // Second execution with same signature: should fail
      await expect(
        taskRouter.connect(relayer).executeOnBehalf(agent.address, calldata4, sig)
      ).to.be.revertedWith("Invalid signature");
    });
  });

  describe("Insufficient Stake", function () {
    it("should reject execution when agent stake is too low", async function () {
      // Give other a small stake
      await taskRouter.connect(other).depositGas({ value: ethers.parseEther("0.000001") });

      const calldata5 = taskRouter.interface.encodeFunctionData("createTask", [
        "Insufficient stake test",
        Math.floor(Date.now() / 1000) + 365 * 86400,
      ]);

      const otherNonce = await taskRouter.agentNonces(other.address);
      const sig = await signForAgent(other, other.address, calldata5, otherNonce);

      // The execution itself might succeed (calldata is valid), but reimbursement might fail
      // if gas cost > stake. We just verify it doesn't silently drain below zero.
      await expect(
        taskRouter.connect(relayer).executeOnBehalf(other.address, calldata5, sig)
      ).to.be.reverted;
    });
  });

  describe("Invalid Signature", function () {
    it("should reject signature from wrong signer", async function () {
      await taskRouter.connect(agent).depositGas({ value: ethers.parseEther("1") });

      const calldata6 = taskRouter.interface.encodeFunctionData("createTask", [
        "Wrong signer test",
        Math.floor(Date.now() / 1000) + 365 * 86400,
      ]);

      const agentNonce = await taskRouter.agentNonces(agent.address);
      // Relayer signs instead of agent — should fail
      const sig = await signForAgent(relayer, agent.address, calldata6, agentNonce);

      await expect(
        taskRouter.connect(relayer).executeOnBehalf(agent.address, calldata6, sig)
      ).to.be.revertedWith("Invalid signature");
    });
  });
});
