const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter Gas Sponsorship Relay", function () {
  let agentRegistry, taskRouter;
  let owner, agentOwner, relayer, taskCreator;
  let agentId;

  beforeEach(async function () {
    [owner, agentOwner, relayer, taskCreator] = await ethers.getSigners();

    // 1. Deploy AgentRegistry (fee = 0.1 ETH)
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    agentRegistry = await AgentRegistry.deploy(ethers.parseEther("0.1"));
    await agentRegistry.waitForDeployment();

    // 2. Deploy TaskRouter (platform fee = 100 BPS = 1%)
    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    taskRouter = await TaskRouter.deploy(agentRegistry.target, 100);
    await taskRouter.waitForDeployment();

    // 3. Register Agent in AgentRegistry
    const tx = await agentRegistry.connect(agentOwner).registerAgent(
      "SponsorAgent",
      "http://endpoint",
      { value: ethers.parseEther("0.1") }
    );
    const receipt = await tx.wait();

    // Parse registered event to get agentId
    const event = receipt.logs
      .map((log) => {
        try {
          return agentRegistry.interface.parseLog(log);
        } catch (e) {
          return null;
        }
      })
      .find((e) => e && e.name === "AgentRegistered");

    agentId = event.args.agentId;
  });

  it("should allow agent to deposit stake", async function () {
    const stakeAmount = ethers.parseEther("1.0");
    await taskRouter.connect(agentOwner).depositStake({ value: stakeAmount });

    const stake = await taskRouter.stakes(agentOwner.address);
    expect(stake).to.equal(stakeAmount);
  });

  it("should execute task assignment on behalf of agent using a signed message", async function () {
    // 1. Task creator creates a task
    const latestBlock = await ethers.provider.getBlock("latest");
    const reward = ethers.parseEther("2.0");
    const deadline = latestBlock.timestamp + 3600;
    const createTaskTx = await taskRouter.connect(taskCreator).createTask(
      "Solve a task",
      deadline,
      { value: reward }
    );
    const createReceipt = await createTaskTx.wait();
    const createEvent = createReceipt.logs
      .map((log) => {
        try {
          return taskRouter.interface.parseLog(log);
        } catch (e) {
          return null;
        }
      })
      .find((e) => e && e.name === "TaskCreated");

    const taskId = createEvent.args.taskId;

    // 2. Deposit stake for agent gas reimbursement
    const stakeAmount = ethers.parseEther("1.0");
    await taskRouter.connect(agentOwner).depositStake({ value: stakeAmount });

    // 3. Prepare calldata for assignTask(taskId, agentId)
    const assignCalldata = taskRouter.interface.encodeFunctionData("assignTask", [
      taskId,
      agentId,
    ]);

    // 4. Sign the calldata
    const nonce = await taskRouter.nonces(agentOwner.address);
    const payloadHash = ethers.solidityPackedKeccak256(
      ["address", "bytes", "uint256", "address"],
      [agentOwner.address, assignCalldata, nonce, taskRouter.target]
    );
    const signature = await agentOwner.signMessage(ethers.getBytes(payloadHash));

    // 5. Relayer calls executeOnBehalf
    const initialRelayerBalance = await ethers.provider.getBalance(relayer.address);
    
    // Set gas price explicitly so we can measure reimbursement accurately
    const gasPrice = ethers.parseUnits("10", "gwei");
    const relayTx = await taskRouter.connect(relayer).executeOnBehalf(
      agentOwner.address,
      assignCalldata,
      signature,
      { gasPrice }
    );
    const relayReceipt = await relayTx.wait();

    // Verify task status is now Assigned
    const task = await taskRouter.tasks(taskId);
    expect(task.status).to.equal(1); // TaskStatus.Assigned

    // Verify relayer was reimbursed (should receive close to gas cost)
    const finalRelayerBalance = await ethers.provider.getBalance(relayer.address);
    const gasSpent = relayReceipt.gasUsed * gasPrice;
    
    // The relayer's balance change should be positive or very small negative because of gas limit reimbursement math
    expect(finalRelayerBalance + gasSpent).to.be.gt(initialRelayerBalance);
  });

  it("should enforce replay protection using nonces", async function () {
    const latestBlock = await ethers.provider.getBlock("latest");
    const reward = ethers.parseEther("2.0");
    const deadline = latestBlock.timestamp + 3600;
    const createTaskTx = await taskRouter.connect(taskCreator).createTask(
      "Solve a task",
      deadline,
      { value: reward }
    );
    const createReceipt = await createTaskTx.wait();
    const createEvent = createReceipt.logs
      .map((log) => {
        try {
          return taskRouter.interface.parseLog(log);
        } catch (e) {
          return null;
        }
      })
      .find((e) => e && e.name === "TaskCreated");

    const taskId = createEvent.args.taskId;

    await taskRouter.connect(agentOwner).depositStake({ value: ethers.parseEther("1.0") });

    const assignCalldata = taskRouter.interface.encodeFunctionData("assignTask", [
      taskId,
      agentId,
    ]);

    const nonce = await taskRouter.nonces(agentOwner.address);
    const payloadHash = ethers.solidityPackedKeccak256(
      ["address", "bytes", "uint256", "address"],
      [agentOwner.address, assignCalldata, nonce, taskRouter.target]
    );
    const signature = await agentOwner.signMessage(ethers.getBytes(payloadHash));

    // First relay works
    await taskRouter.connect(relayer).executeOnBehalf(
      agentOwner.address,
      assignCalldata,
      signature
    );

    // Second relay of same signature/nonce should fail
    await expect(
      taskRouter.connect(relayer).executeOnBehalf(
        agentOwner.address,
        assignCalldata,
        signature
      )
    ).to.be.revertedWith("Invalid signature");
  });

  it("should fail if agent has insufficient stake", async function () {
    const latestBlock = await ethers.provider.getBlock("latest");
    const reward = ethers.parseEther("2.0");
    const deadline = latestBlock.timestamp + 3600;
    const createTaskTx = await taskRouter.connect(taskCreator).createTask(
      "Solve a task",
      deadline,
      { value: reward }
    );
    const createReceipt = await createTaskTx.wait();
    const createEvent = createReceipt.logs
      .map((log) => {
        try {
          return taskRouter.interface.parseLog(log);
        } catch (e) {
          return null;
        }
      })
      .find((e) => e && e.name === "TaskCreated");

    const taskId = createEvent.args.taskId;

    // Stake is only 1 wei (virtually 0)
    await taskRouter.connect(agentOwner).depositStake({ value: 1n });

    const assignCalldata = taskRouter.interface.encodeFunctionData("assignTask", [
      taskId,
      agentId,
    ]);

    const nonce = await taskRouter.nonces(agentOwner.address);
    const payloadHash = ethers.solidityPackedKeccak256(
      ["address", "bytes", "uint256", "address"],
      [agentOwner.address, assignCalldata, nonce, taskRouter.target]
    );
    const signature = await agentOwner.signMessage(ethers.getBytes(payloadHash));

    await expect(
      taskRouter.connect(relayer).executeOnBehalf(
        agentOwner.address,
        assignCalldata,
        signature
      )
    ).to.be.revertedWith("Insufficient stake");
  });
});
